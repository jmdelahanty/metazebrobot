"""Generate printable dish labels with QR codes.

Produces a PNG image sized for standard label stock (62mm x 29mm at 300 DPI).
The QR code encodes the dish_id so USB barcode scanners and phone cameras can
read it.
"""

from __future__ import annotations

import io
from typing import Optional

import qrcode
from PIL import Image, ImageDraw, ImageFont

# Label dimensions: 62mm x 29mm at 300 DPI
LABEL_WIDTH = 732
LABEL_HEIGHT = 342


def generate_dish_label(
    dish_id: str,
    genotype: Optional[str] = None,
    dof: Optional[str] = None,
    fish_count: Optional[int] = None,
    container_type: Optional[str] = None,
) -> bytes:
    """Generate a PNG label image for a dish.

    Args:
        dish_id: Dish identifier (encoded in QR code).
        genotype: Genotype string (truncated if long).
        dof: Date of fertilisation (YYYYMMDD).
        fish_count: Number of fish.
        container_type: Container type string.

    Returns:
        PNG image bytes.
    """
    img = Image.new("RGB", (LABEL_WIDTH, LABEL_HEIGHT), "white")
    draw = ImageDraw.Draw(img)

    # Use default font at different sizes (no external font files needed)
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large

    # QR code on the right side
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(dish_id)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Scale QR to fit label height with padding
    qr_size = LABEL_HEIGHT - 20
    qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
    qr_x = LABEL_WIDTH - qr_size - 10
    img.paste(qr_img, (qr_x, 10))

    # Text area is left of the QR code
    text_width = qr_x - 20
    x, y = 15, 15

    # Dish ID (large)
    draw.text((x, y), dish_id, fill="black", font=font_large)
    y += 36

    # Genotype (truncated if needed)
    if genotype:
        display_geno = genotype if len(genotype) <= 40 else genotype[:37] + "..."
        draw.text((x, y), display_geno, fill="#333333", font=font_medium)
    y += 26

    # DOF
    if dof:
        dof_display = f"{dof[:4]}-{dof[4:6]}-{dof[6:]}" if len(dof) == 8 else dof
        draw.text((x, y), f"DOF: {dof_display}", fill="#555555", font=font_small)
    y += 20

    # Fish count + container
    details = []
    if fish_count is not None:
        details.append(f"Fish: {fish_count}")
    if container_type:
        details.append(container_type.replace("_", " "))
    if details:
        draw.text((x, y), " | ".join(details), fill="#555555", font=font_small)

    # Border
    draw.rectangle([(0, 0), (LABEL_WIDTH - 1, LABEL_HEIGHT - 1)], outline="#cccccc")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
