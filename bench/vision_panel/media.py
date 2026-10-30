"""No decode/render helpers: root supplies exact processed PNG extraction receipts."""
from .protocol import require


def normalize_check(path):
    from PIL import Image
    with Image.open(path) as im:
        require(im.format == 'PNG' and im.mode == 'RGB' and not im.info and not im.getexif(), 'non-neutral PNG')
        require(1 <= im.width <= 8192 and 1 <= im.height <= 8192, 'image bounds')
        im.verify()
