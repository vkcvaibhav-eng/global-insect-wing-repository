"""Synthetic, non-sensitive demonstration assets.

The drawing is intentionally schematic. It exists to exercise upload,
digitization, review, and export and must not be treated as an anatomical or
taxonomic reference.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


DEMO_IMAGE_WIDTH = 1_600
DEMO_IMAGE_HEIGHT = 900

# Locations corresponding loosely to the illustrative JSON descriptions. They
# are only seed coordinates for exercising the software workflow.
DEMO_LANDMARK_PIXELS: tuple[tuple[float, float], ...] = (
    (178.0, 524.0),
    (304.0, 356.0),
    (595.0, 235.0),
    (1_330.0, 260.0),
    (1_180.0, 385.0),
    (835.0, 435.0),
    (1_120.0, 580.0),
    (1_292.0, 690.0),
    (350.0, 690.0),
    (700.0, 615.0),
)


def synthetic_wing_png() -> bytes:
    """Return a deterministic PNG containing a labeled wing-like schematic."""

    image = Image.new("RGB", (DEMO_IMAGE_WIDTH, DEMO_IMAGE_HEIGHT), (246, 248, 250))
    draw = ImageDraw.Draw(image)
    outline = [
        (160, 525),
        (270, 370),
        (560, 225),
        (950, 175),
        (1_320, 245),
        (1_445, 415),
        (1_390, 610),
        (1_295, 705),
        (1_020, 755),
        (600, 735),
        (340, 695),
    ]
    draw.polygon(outline, fill=(231, 241, 244), outline=(56, 78, 83), width=5)

    vein_color = (66, 86, 91)
    vein_width = 5
    veins = [
        [(178, 524), (304, 356), (595, 235), (1_330, 260)],
        [(178, 524), (835, 435), (1_180, 385), (1_330, 260)],
        [(304, 356), (835, 435)],
        [(178, 524), (350, 690), (700, 615), (835, 435)],
        [(835, 435), (1_120, 580), (1_292, 690)],
        [(700, 615), (1_120, 580)],
        [(350, 690), (1_292, 690)],
        [(1_180, 385), (1_120, 580)],
    ]
    for vein in veins:
        draw.line(vein, fill=vein_color, width=vein_width, joint="curve")

    title_font = ImageFont.load_default(size=26)
    body_font = ImageFont.load_default(size=18)
    draw.rounded_rectangle((40, 35, 650, 118), radius=12, fill=(255, 255, 255), outline=(150, 160, 165), width=2)
    draw.text((62, 51), "SYNTHETIC RIGHT-FOREWING DEMO", fill=(25, 41, 46), font=title_font)
    draw.text((62, 86), "Not a taxonomic reference specimen", fill=(126, 42, 42), font=body_font)

    return_bytes = BytesIO()
    image.save(return_bytes, format="PNG", optimize=True)
    return return_bytes.getvalue()
