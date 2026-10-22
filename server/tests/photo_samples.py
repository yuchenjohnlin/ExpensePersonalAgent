"""Photos made in code, so tests need no image files."""
from io import BytesIO

from PIL import Image, ImageDraw


def drawing(kind="PNG", size=(2400, 1500), shade=0) -> bytes:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for n in range(0, size[0], 60):
        draw.line((n, 0, size[0] - n, size[1]), fill=((n + shade) % 255, 80, 160), width=7)
    draw.rectangle((300, 300, 900, 700), fill=(20, 120, 40))
    out = BytesIO()
    image.save(out, format=kind)
    return out.getvalue()
