"""Optional diagnostics: disk failures never become transport failures."""
from pathlib import Path
import shutil


class Archive:
    # Reserve 128 MiB for the OS/operator. Capacity is checked before every
    # write; opt-in evidence stops permanently at the first capacity/I/O failure.
    minimum_free = 128 * 1024 * 1024

    def __init__(self, directory):
        self.directory = Path(directory) if directory is not None else None
        self.enabled = directory is not None
        self.media = None
        if self.enabled:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.enabled = False

    def check(self):
        if self.enabled:
            try:
                if shutil.disk_usage(self.directory).free < self.minimum_free:
                    self.enabled = False
            except OSError:
                self.enabled = False
        return self.enabled

    def text(self, name, value, mode='a'):
        if not self.check():
            return
        try:
            with (self.directory / name).open(mode) as output:
                output.write(value)
        except OSError:
            self.enabled = False

    def packets(self, name, data):
        if not self.check():
            return
        try:
            if self.media is None:
                self.media = (self.directory / name).open('wb')
            self.media.write(data)
            self.media.flush()
        except OSError:
            self.enabled = False

    def close(self):
        if self.media is not None:
            try:
                self.media.close()
            except OSError:
                self.enabled = False
            self.media = None


class MuxSink:
    """Retain only the bounded startup fragment required for decoder templates."""
    def __init__(self, archive, name):
        self.archive, self.name = archive, name
        self.prefix = bytearray()

    def writable(self):
        return True

    def write(self, data):
        if self.prefix is not None:
            if len(self.prefix) + len(data) > 1024 * 1024:
                raise RuntimeError('egress-header-limit')
            self.prefix.extend(data)
        self.archive.packets(self.name, data)
        return len(data)
