from io import BytesIO
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.schemas.analysis import Agent1VisualAudit, Agent2GroundedExplanation


def render_analysis_report_pdf(
    image_path: Path,
    title: str,
    question: str,
    audit: Agent1VisualAudit,
    explanation: Agent2GroundedExplanation,
) -> bytes:
    """Renders an annotated PDF report with green verified & yellow unverified boxes."""
    with Image.open(image_path) as im:
        annotated = im.convert("RGB").copy()
        w, h = annotated.size

    draw = ImageDraw.Draw(annotated)
    for region in audit.regions:
        px = region.bbox_px or [
            int(region.bbox_1000[1] * w / 1000),
            int(region.bbox_1000[0] * h / 1000),
            int(region.bbox_1000[3] * w / 1000),
            int(region.bbox_1000[2] * h / 1000),
        ]
        color = (141, 182, 0) if region.status == "VERIFIED" else (255, 182, 39)
        draw.rectangle(px, outline=color, width=4)

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        annotated.save(tmp.name, format="PNG")
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        pw, ph = letter

        c.setFont("Helvetica-Bold", 18)
        c.drawString(42, ph - 48, f"VisionGuard Tutor Report: {title[:52]}")
        c.setFont("Helvetica", 10)
        c.drawString(42, ph - 66, f"Question: {question[:95]}")

        max_w, max_h = pw - 84, 240
        scale = min(max_w / w, max_h / h)
        dw, dh = w * scale, h * scale
        c.drawImage(ImageReader(tmp.name), 42, ph - 84 - dh, width=dw, height=dh)

        y = ph - 106 - dh
        c.setFont("Helvetica-Bold", 12)
        c.drawString(42, y, "Grounded Steps (Verified Regions Only)")
        y -= 18
        c.setFont("Helvetica", 9.5)
        for step in explanation.steps:
            if y < 90:
                c.showPage()
                y = ph - 50
                c.setFont("Helvetica", 9.5)
            line = f"{step.step_number}. [{step.cited_box_id}] {step.heading}: {step.explanation[:105]}"
            c.drawString(42, y, line)
            y -= 15

        if explanation.rubric:
            y -= 10
            c.setFont("Helvetica-Bold", 12)
            c.drawString(42, y, f"Rubric Score: {explanation.rubric.score_out_of_10}/10")
            y -= 16
            c.setFont("Helvetica", 9.5)
            c.drawString(42, y, explanation.rubric.feedback_summary[:105])
            y -= 18

        if explanation.unverified_warnings:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(42, y, "Guardrail Warnings (UNVERIFIED Regions)")
            y -= 16
            c.setFont("Helvetica", 9.5)
            for warn in explanation.unverified_warnings:
                c.drawString(42, y, f"- {warn.box_id}: {warn.warning_message[:100]}")
                y -= 14

        c.showPage()
        c.save()
        return buf.getvalue()
