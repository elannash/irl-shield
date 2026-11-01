"""Delivery privacy checks on tracked working text, including archived evidence.

Git commit history is not scanned; archived files in the working tree are.
"""
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
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
            ('owner-cgroup', 'user-' + '1000.slice'),
            ('owner-service', 'user@' + '1000.service'),
            ('mac-mirror', '/tmp/' + 'irl-shield'),
            ('mac-mirror', '/private/tmp/' + 'irl-shield'),
            ('mac-mirror', '/tmp/' + 'shield-'),
            ('mac-mirror', '/private/tmp/' + 'shield-'),
        )
        hostnames = re.compile(r'(?<![\w-])(?:' + '|'.join(re.escape(host) for host in (
            'MacBook' + 'Pro', 'elan-' + 'linux', 'linux-' + 'pc'))
            + r')(?:\.[a-z0-9-]+)*(?![\w-])', re.IGNORECASE)
        tailnet = ipaddress.IPv4Network('100.64.0.0/10')
        tailnet_v6 = ipaddress.IPv6Network('fd7a:115c:a1e0::/48')
        # These six literal fixtures predate the scrub and exercise ACL boundaries.
        # Values are allowed individually in any text; no file, subnet or prefix is exempt.
        synthetic_ipv4 = {
            '100.80.1.2', '100.80.2.3', '100.80.4.5',
            '100.80.90.100', '100.100.10.20', '100.100.100.100',
        }
        # Require the format signature too; renaming tracked text must not exempt it.
        binary_signatures = {
            '.png': (b'\x89PNG\r\n\x1a\n',),
            '.ttf': (b'\x00\x01\x00\x00',),
        }
        addresses = re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?!\d|\.\d)')
        addresses_v6 = re.compile(
            r'(?<![\w:])(?:[0-9a-f]{0,4}:){2,}[0-9a-f:.]*(?:%[\w.-]+)?(?![\w:])',
            re.IGNORECASE)
        # Decode only literal JSON slash/backslash and Unicode escapes, at most two layers.
        escapes = re.compile(r'\\(?:u([0-9a-fA-F]{4})|([\\/]))')
        findings = []
        scanned = 0
        for raw in paths:
            relative = Path(os.fsdecode(raw))
            self.assertFalse(relative.is_absolute() or '..' in relative.parts,
                             'unsafe tracked path')
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
                if data.startswith(binary_signatures.get(relative.suffix.lower(), ())):
                    continue
            # Only these exact sealed bytes are exempt, after path/type checks.
            if relative.as_posix() == 'fixtures/fresh-heldout-v2/nonreuse.json':
                self.assertTrue(stat.S_ISREG(mode), 'sealed nonreuse must be a regular file')
                self.assertEqual(hashlib.sha256(data).hexdigest(),
                                 '5ee0a6d68d0aed14f93a389e3dc23430b605e89a6a68a0c78064464f0f92546e',
                                 'sealed nonreuse bytes changed')
                continue
            self.assertNotIn(b'\0', data, 'NUL in tracked text: ' + str(relative))
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                self.fail('undecodable tracked text: ' + str(relative))
            scanned += 1
            for number, line in enumerate(text.splitlines(), 1):
                for _ in range(2):
                    line = escapes.sub(lambda match: chr(int(match[1], 16))
                                       if match[1] else match[2], line)
                for label, prefix in prefixes:
                    if prefix in line:
                        findings.append(f'{relative}:{number}: {label}')
                if hostnames.search(line):
                    findings.append(f'{relative}:{number}: owner-hostname')
                for match in addresses.finditer(line):
                    try:
                        address = ipaddress.IPv4Address(match.group())
                    except ipaddress.AddressValueError:
                        continue
                    if address not in tailnet or match.group() in synthetic_ipv4:
                        continue
                    # Only the exact policy CIDR token is a declaration, never another host/CIDR.
                    before = line[match.start() - 1:match.start()] if match.start() else ''
                    canonical = (match.group() == str(tailnet.network_address)
                                 and not re.search(r'[\w./]', before)
                                 and re.match(r'/10(?![\w/]|\.\w)', line[match.end():]))
                    if not canonical:
                        findings.append(f'{relative}:{number}: tailnet-host')
                for match in addresses_v6.finditer(line):
                    try:
                        address = ipaddress.IPv6Address(match.group().rstrip('.'))
                    except ipaddress.AddressValueError:
                        continue
                    if address not in tailnet_v6:
                        continue
                    before = line[match.start() - 1:match.start()] if match.start() else ''
                    canonical = (match.group().lower() == str(tailnet_v6.network_address)
                                 and not re.search(r'[\w./]', before)
                                 and re.match(r'/48(?![\w/]|\.\w)', line[match.end():]))
                    if not canonical:
                        findings.append(f'{relative}:{number}: tailnet-ipv6-host')
        self.assertGreater(scanned, 0, 'no tracked text was scanned')
        self.assertEqual(findings, [], 'private owner identifiers in tracked text:\n'
                         + '\n'.join(findings))


class RepositoryPrivacyInventory(unittest.TestCase):
    """Exercise the shipped scan entry point, with actual synthetic Git inventory."""

    def fixture(self, temporary, payload=b'public fixture\n', name='report.txt'):
        root = Path(temporary)
        (root / 'tests').mkdir()
        (root / 'tests/test_repository_privacy.py').write_bytes(Path(__file__).read_bytes())
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        subprocess.run(['git', '-c', 'init.templateDir=', 'init', '--quiet', str(root)],
                       check=True, capture_output=True, timeout=10)
        subprocess.run(['git', '-C', str(root), 'add', '--', 'tests', name],
                       check=True, capture_output=True, timeout=10)
        return root

    def invoke(self, root):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('PYTHONPATH', None)
        return subprocess.run([sys.executable, 'tests/test_repository_privacy.py',
            'RepositoryPrivacy.test_tracked_text_contains_no_private_owner_identifiers'],
            cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=20)

    def test_private_text_is_rejected_through_git_inventory(self):
        host = '100.95.' + '6.7'
        home = '/home/' + 'elan'
        ula = 'fd7a:115c:' + 'a1e0::1234'
        cases = (
            ('ipv4-sentence-period', 'Host ' + host + '.', 'tailnet-host'),
            ('ipv4-sentence-punctuation', '(' + host + '),', 'tailnet-host'),
            ('owner-address', '100.109.' + '49.77', 'tailnet-host'),
            ('allowlist-neighbor', '100.80.1.2 ' + host, 'tailnet-host'),
            ('allowlist-prefix', '100.80.' + '1.20', 'tailnet-host'),
            ('host-with-cidr', host + '/32', 'tailnet-host'),
            ('noncanonical-cidr', '100.64.' + '0.0/11', 'tailnet-host'),
            ('bare-policy-address', '100.64.' + '0.0', 'tailnet-host'),
            ('policy-cidr-suffix', '100.64.0.0/10' + '/32', 'tailnet-host'),
            ('mac-hostname', 'MacBook' + 'Pro.lan', 'owner-hostname'),
            ('linux-hostname', 'elan-' + 'linux', 'owner-hostname'),
            ('linux-alias-hostname', 'LINUX-' + 'PC', 'owner-hostname'),
            ('linux-home', home + '/project', 'linux-home'),
            ('mac-home', '/Users/' + 'elannash/project', 'mac-home'),
            ('owner-tmp', '/tmp/' + 'claude-1000/project', 'owner-tmp'),
            ('owner-runtime', '/run/user/' + '1000/bus', 'owner-runtime'),
            ('owner-cgroup', '/user.slice/user-' + '1000.slice', 'owner-cgroup'),
            ('owner-service', '/user.slice/user@' + '1000.service', 'owner-service'),
            ('mirror', '/tmp/' + 'irl-shield-mac/project', 'mac-mirror'),
            ('private-mirror', '/private/tmp/' + 'shield-q/project', 'mac-mirror'),
            ('json-escaped-slashes', '{"path":"' + home.replace('/', r'\/') + '"}', 'linux-home'),
            ('json-unicode-home', r'{"path":"\u002fhome\u002f' + 'elan/project"}', 'linux-home'),
            ('json-unicode-host', r'{"host":"\u004d' + 'acBookPro.lan"}', 'owner-hostname'),
            ('json-unicode-ip', r'{"host":"\u0031' + host[1:] + '"}', 'tailnet-host'),
            ('json-nested-escape', home.replace('/', r'\\u002f'), 'linux-home'),
            ('tailnet-ipv6', '[' + ula + ']:443', 'tailnet-ipv6-host'),
            ('tailnet-ipv6-period', ula.upper() + '.', 'tailnet-ipv6-host'),
            ('tailnet-ipv6-expanded', 'fd7a:115c:' + 'a1e0:0000:0000:0000:0000:1234', 'tailnet-ipv6-host'),
            ('tailnet-ipv6-scoped', ula + '%test0', 'tailnet-ipv6-host'),
            ('tailnet-ipv6-cidr', ula + '/128', 'tailnet-ipv6-host'),
            ('tailnet-ipv6-bare-policy', 'fd7a:115c:' + 'a1e0::', 'tailnet-ipv6-host'),
            ('tailnet-ipv6-policy-suffix', 'fd7a:115c:a1e0::/48' + '/128', 'tailnet-ipv6-host'),
            ('tailnet-ipv6-noncanonical-cidr', 'fd7a:115c:' + 'a1e0::/64', 'tailnet-ipv6-host'),
        )
        for name, payload, reason in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory(prefix='shield-privacy-') as temporary:
                root = self.fixture(temporary, (payload + '\n').encode())
                result = self.invoke(root)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn('private owner identifiers in tracked text', result.stdout)
                self.assertIn('report.txt:1: ' + reason, result.stdout)

    def test_public_text_binary_and_exact_synthetic_values_are_allowed(self):
        text = ('Public host 203.0.113.9; loopbacks 127.0.0.1, ::1, [::1]:80.\n'
                'Policy 100.64.0.0/10. Policy fd7a:115c:a1e0::/48.\n'
                '100.80.1.2 100.80.2.3 100.80.4.5 100.80.90.100 '
                '100.100.10.20 100.100.100.100\n'
                'OWNER_HOME WORKTREE OWNER_UID MAC_HOST; public.invalid\n'
                r'JSON {"path":"\/tmp\/public","letter":"\u0041"}' + '\n')
        with tempfile.TemporaryDirectory(prefix='shield-privacy-') as temporary:
            root = self.fixture(temporary, text.encode())
            (root / 'image.png').write_bytes(b'\x89PNG\r\n\x1a\n\x00\xffbinary fixture')
            (root / 'font.ttf').write_bytes(b'\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
            (root / 'public-text.png').write_text('Public text with an image suffix\n')
            # Only a link's text is scanned, even with an allowed binary suffix.
            (root / 'untracked-target.txt').write_text('/home/' + 'elan/private')
            (root / 'public-link.png').symlink_to('untracked-target.txt')
            subprocess.run(['git', '-C', str(root), 'add', '--',
                            'image.png', 'font.ttf', 'public-text.png', 'public-link.png'],
                           check=True, capture_output=True, timeout=10)
            result = self.invoke(root)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('Ran 1 test', result.stdout)

    def test_nonbinary_undecodable_and_nul_text_fail_closed(self):
        private = ('/home/' + 'elan/project\n').encode()
        for name, filename, payload, reason in (
                ('undecodable', 'report.txt', b'\xffprivate fixture',
                 'undecodable tracked text: report.txt'),
                ('nul', 'report.txt', b'public\0text', 'NUL in tracked text: report.txt'),
                ('text-png', 'report.png', private, 'report.png:1: linux-home'),
                ('text-ttf', 'report.ttf', private, 'report.ttf:1: linux-home'),
                ('ascii-font-tag', 'report.ttf', b'true ' + private, 'report.ttf:1: linux-home'),
                ('ascii-otto-tag', 'report.ttf', b'OTTO ' + private, 'report.ttf:1: linux-home'),
                ('undecodable-png', 'report.png', b'\xffprivate fixture',
                 'undecodable tracked text: report.png'),
                ('nul-ttf', 'report.ttf', b'public\0text', 'NUL in tracked text: report.ttf')):
            with self.subTest(case=name), tempfile.TemporaryDirectory(prefix='shield-privacy-') as temporary:
                root = self.fixture(temporary, payload, name=filename)
                result = self.invoke(root)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(reason, result.stdout)

    def test_missing_nonfile_and_symlink_parent_fail_closed(self):
        for name, reason in (('missing', 'FileNotFoundError'),
                             ('nonfile', 'non-file tracked entry'),
                             ('symlink-parent', 'refusing a tracked path below a symlink')):
            with self.subTest(case=name), tempfile.TemporaryDirectory(prefix='shield-privacy-') as temporary:
                root = self.fixture(temporary, name='nested/report.txt')
                (root / 'nested/report.txt').unlink()
                if name == 'nonfile':
                    (root / 'nested/report.txt').mkdir()
                elif name == 'symlink-parent':
                    (root / 'nested').rmdir()
                    (root / 'nested').symlink_to('not-a-real-directory')
                result = self.invoke(root)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(reason, result.stdout)

    def test_symlink_target_is_scanned_without_dereferencing(self):
        with tempfile.TemporaryDirectory(prefix='shield-privacy-') as temporary:
            root = self.fixture(temporary)
            (root / 'report.txt').unlink()
            (root / 'report.txt').symlink_to('/home/' + 'elan/not-a-real-target')
            result = self.invoke(root)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn('report.txt:1: linux-home', result.stdout)
            self.assertNotIn('FileNotFoundError', result.stdout)

    def test_sealed_exception_rejects_other_bytes_and_nearby_paths(self):
        for name, reason in (
                ('fixtures/fresh-heldout-v2/nonreuse.json', 'sealed nonreuse bytes changed'),
                ('fixtures/fresh-heldout-v2/manifest.json', 'linux-home'),
                ('fixtures/fresh-heldout-v2/another.json', 'linux-home')):
            with self.subTest(path=name), tempfile.TemporaryDirectory(prefix='shield-privacy-') as temporary:
                root = self.fixture(temporary, ('/home/' + 'elan/fixture').encode(), name)
                result = self.invoke(root)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(reason, result.stdout)

    def test_git_failure_wrong_root_and_empty_inventory_fail_closed(self):
        for name, reason in (('git-failure', 'CalledProcessError'),
                             ('wrong-root', 'privacy check must run in its own repository'),
                             ('empty-inventory', 'empty or malformed tracked inventory')):
            with self.subTest(case=name), tempfile.TemporaryDirectory(prefix='shield-privacy-') as temporary:
                root = self.fixture(temporary)
                if name == 'git-failure':
                    (root / '.git').rename(root / 'not-git')
                elif name == 'wrong-root':
                    nested = root / 'nested'
                    (nested / 'tests').mkdir(parents=True)
                    (nested / 'tests/test_repository_privacy.py').write_bytes(Path(__file__).read_bytes())
                    root = nested
                else:
                    subprocess.run(['git', '-C', str(root), 'rm', '--cached', '-r', '--quiet', '.'],
                                   check=True, capture_output=True, timeout=10)
                result = self.invoke(root)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(reason, result.stdout)

    def test_malformed_and_unsafe_inventory_fail_before_file_reads(self):
        # Git cannot normally emit these paths. Inject corrupt metadata only after
        # the real Git command succeeds, keeping the scan's CLI and file boundary.
        wrapper = '''
import runpy
import subprocess
import sys
from unittest.mock import patch
inventory = bytes.fromhex(sys.argv[1])
sys.argv = ['tests/test_repository_privacy.py',
            'RepositoryPrivacy.test_tracked_text_contains_no_private_owner_identifiers']
original = subprocess.run
def metadata(*args, **kwargs):
    result = original(*args, **kwargs)
    if args[0][-2:] == ['ls-files', '-z']:
        result.stdout = inventory
    return result
with patch('subprocess.run', side_effect=metadata):
    runpy.run_path(sys.argv[0], run_name='__main__')
'''
        cases = (('missing-terminator', b'report.txt', 'empty or malformed tracked inventory'),
                 ('empty-entry', b'report.txt\0\0', 'empty tracked path'),
                 ('absolute-entry', None, 'unsafe tracked path'),
                 ('parent-entry', None, 'unsafe tracked path'))
        for name, inventory, reason in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory(prefix='shield-privacy-') as temporary:
                root = self.fixture(temporary)
                if name == 'absolute-entry':
                    inventory = os.fsencode(root / 'report.txt') + b'\0'
                elif name == 'parent-entry':
                    inventory = os.fsencode(Path('..') / root.name / 'report.txt') + b'\0'
                env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
                env.pop('PYTHONPATH', None)
                result = subprocess.run([sys.executable, '-c', wrapper, inventory.hex()],
                    cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=20)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(reason, result.stdout)


if __name__ == '__main__':
    unittest.main()
