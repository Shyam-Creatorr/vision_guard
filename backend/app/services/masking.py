from io import BytesIO
from pathlib import Path
import uuid

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.core.config import get_settings
from app.schemas.analysis import AuditedRegion


def _get_font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def generate_blank_label_diagram(
    source_image_path: str | Path,
    regions: list[AuditedRegion],
) -> tuple[str, list[dict]]:
    """
    Masks ONLY VERIFIED label boxes with numbered blank pills ([1], [2], ...).
    UNVERIFIED regions are visibly marked with Mango Yellow lock warning stripes and NEVER included in blanks.
    Returns (blank_image_key, blank_items).
    """
    settings = get_settings()
    with Image.open(source_image_path) as img:
        working = img.convert("RGB").copy()
        w, h = working.size

    draw = ImageDraw.Draw(working)
    font = _get_font(max(18, int(h * 0.026)))
    blank_items: list[dict] = []
    blank_num = 1

    for region in regions:
        px = region.bbox_px
        if not px or len(px) != 4:
            ymin, xmin, ymax, xmax = region.bbox_1000
            px = [
                int(xmin * w / 1000),
                int(ymin * h / 1000),
                int(xmax * w / 1000),
                int(ymax * h / 1000),
            ]
        x1, y1, x2, y2 = px
        pad = 4
        rx1, ry1 = max(0, x1 - pad), max(0, y1 - pad)
        rx2, ry2 = min(w, x2 + pad), min(h, y2 + pad)

        if region.status in ("VERIFIED", "verified", "user_confirmed") and region.label_text.strip():
            # Mask label text cleanly with beige/white pill & numbered blank
            draw.rounded_rectangle(
                [rx1, ry1, rx2, ry2],
                radius=12,
                fill=(246, 240, 227),
                outline=(141, 182, 0),
                width=4,
            )
            tag = f"[{blank_num}] _____"
            draw.text((rx1 + 10, ry1 + max(4, (ry2 - ry1 - 20) // 2)), tag, fill=(14, 15, 16), font=font)
            blank_items.append(
                {
                    "blank_number": blank_num,
                    "box_id": region.box_id,
                    "expected_label": region.label_text,
                    "bbox_1000": region.bbox_1000,
                    "bbox_px": px,
                }
            )
            blank_num += 1
        elif region.status in ("UNVERIFIED", "unverified_blocked", "suggested", "rejected"):
            # Draw explicit Mango Yellow lock frame — never quizzed
            draw.rounded_rectangle(
                [rx1, ry1, rx2, ry2],
                radius=10,
                outline=(255, 182, 39),
                width=4,
            )
            draw.rectangle([rx1, max(0, ry1 - 24), min(w, rx1 + 125), ry1], fill=(255, 182, 39))
            draw.text((rx1 + 6, max(0, ry1 - 21)), "LOCKED", fill=(14, 15, 16), font=_get_font(15))

    upload_dir = settings.upload_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    blank_key = f"{uuid.uuid4().hex}_blank.png"
    working.save(upload_dir / blank_key, format="PNG")
    return blank_key, blank_items


def render_worksheet_pdf(
    blank_image_path: Path,
    title: str,
    blank_count: int,
    unverified_count: int,
) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    pw, ph = letter

    c.setFont("Helvetica-Bold", 18)
    c.drawString(42, ph - 50, f"VisionGuard Practice Worksheet: {title[:55]}")
    c.setFont("Helvetica", 10)
    c.drawString(
        42,
        ph - 68,
        f"Fill in the {blank_count} verified blanks below. ({unverified_count} illegible regions locked from quiz.)",
    )

    with Image.open(blank_image_path) as im:
        iw, ih = im.size
    max_w = pw - 84
    max_h = ph - 260
    scale = min(max_w / iw, max_h / ih)
    draw_w, draw_h = iw * scale, ih * scale
    c.drawImage(ImageReader(str(blank_image_path)), 42, ph - 90 - draw_h, width=draw_w, height=draw_h)

    y_cursor = ph - 115 - draw_h
    c.setFont("Helvetica-Bold", 11)
    c.drawString(42, y_cursor, "Answer Lines:")
    c.setFont("Helvetica", 11)
    for n in range(1, min(blank_count + 1, 11)):
        y_cursor -= 20
        if y_cursor < 42:
            break
        c.drawString(42, y_cursor, f"[{n}] __________________________________________________")

    c.showPage()
    c.save()
    return buf.getvalue()
