"""Delivery privacy checks against tracked working bytes, including history."""
import ipaddress
import os
from pathlib import Path
import re
import stat
import subprocess
import unittest


class RepositoryPrivacy(unittest.TestCase):
    def test_tracked_text_contains_no_private_owner_identifiers(self):
        root = Path(__file__).resolve().parents[1]
        git_root = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                                  check=True, capture_output=True).stdout
        self.assertEqual(Path(os.fsdecode(git_root.rstrip(b'\n'))).resolve(), root,
                         'privacy check must run in its own repository')
        inventory = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'],
                                   check=True, capture_output=True).stdout
        self.assertTrue(inventory.endswith(b'\0'), 'empty or malformed tracked inventory')
        paths = inventory[:-1].split(b'\0')
        self.assertTrue(all(paths), 'empty tracked path')
        prefixes = (
            ('linux-home', '/home/' + 'elan'),
            ('mac-home', '/Users/' + 'elannash'),
            ('owner-tmp', '/tmp/' + 'claude-1000'),
            ('owner-runtime', '/run/user/' + '1000'),
        )
        tailnet = ipaddress.IPv4Network('100.64.0.0/10')
        addresses = re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')
        findings = []
        scanned = 0
        for raw in paths:
            relative = Path(os.fsdecode(raw))
            self.assertFalse(relative.is_absolute() or '..' in relative.parts,
                             'unsafe tracked path')
            # This one sealed ledger keeps its original bytes until authorized unsealing.
            if relative.as_posix() == 'fixtures/fresh-heldout-v2/nonreuse.json':
                continue
            for parent in relative.parents:
                self.assertFalse((root / parent).is_symlink(),
                                 'refusing a tracked path below a symlink: ' + str(relative))
            path = root / relative
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                data = os.fsencode(os.readlink(path))
            else:
                self.assertTrue(stat.S_ISREG(mode), 'non-file tracked entry: ' + str(relative))
                data = path.read_bytes()
            if b'\0' in data:
                continue
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                continue
            scanned += 1
            for number, line in enumerate(text.splitlines(), 1):
                for label, prefix in prefixes:
                    if prefix in line:
                        findings.append(f'{relative}:{number}: {label}')
                for match in addresses.finditer(line):
                    try:
                        address = ipaddress.IPv4Address(match.group())
                    except ipaddress.AddressValueError:
                        continue
                    if address not in tailnet:
                        continue
                    # Public policy CIDR is allowed as a complete token, never a bare host.
                    before = line[match.start() - 1:match.start()] if match.start() else ''
                    canonical = (match.group() == str(tailnet.network_address)
                                 and not re.search(r'[\w./]', before)
                                 and re.match(r'/10(?![\w./])', line[match.end():]))
                    if not canonical:
                        findings.append(f'{relative}:{number}: tailnet-host')
        self.assertGreater(scanned, 0, 'no tracked text was scanned')
        self.assertEqual(findings, [], 'private owner identifiers in tracked text:\n'
                         + '\n'.join(findings))


if __name__ == '__main__':
    unittest.main()
