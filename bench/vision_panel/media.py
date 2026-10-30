"""No decode/render helpers: root supplies exact processed PNG extraction receipts."""
import struct

from .protocol import require


def normalize_check(path):
    # Reject even unknown ancillary chunks; Pillow's info dict does not expose
    # every possible source metadata channel.
    with open(path, 'rb') as f:
        require(f.read(8) == b'\x89PNG\r\n\x1a\n', 'PNG signature')
        kinds = []
        while True:
            header = f.read(8)
            require(len(header) == 8, 'truncated PNG chunk')
            size, kind = struct.unpack('>I4s', header)
            require(kind in (b'IHDR', b'IDAT', b'IEND') and size <= 64 * 1024 * 1024, 'PNG metadata/unknown chunk')
            require(len(f.read(size + 4)) == size + 4, 'truncated PNG payload')
            kinds.append(kind)
            if kind == b'IEND':
                require(not f.read(1), 'PNG trailing metadata')
                break
        require(kinds[0] == b'IHDR' and kinds.count(b'IHDR') == 1 and b'IDAT' in kinds, 'PNG chunk order')
    from PIL import Image
    with Image.open(path) as im:
        require(im.format == 'PNG' and im.mode == 'RGB' and not im.info, 'non-neutral PNG')
        require(1 <= im.width <= 8192 and 1 <= im.height <= 8192, 'image bounds')
        im.verify()
