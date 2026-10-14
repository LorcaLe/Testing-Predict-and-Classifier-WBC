import math

import pymupdf

from common import config
from common.contracts import WatermarkSettings


class UnsupportedDocument(ValueError):
    pass


def open_pdf(data: bytes):
    if not data.startswith(b"%PDF-"):
        raise UnsupportedDocument("Upload a valid PDF document.")
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as error:
        raise UnsupportedDocument("This PDF is damaged or cannot be read.") from error
    if document.needs_pass:
        document.close()
        raise UnsupportedDocument("Password-protected PDFs are not supported.")
    if not 1 <= document.page_count <= config.MAX_PAGES:
        document.close()
        raise UnsupportedDocument(f"Upload a PDF with 1 to {config.MAX_PAGES} pages.")
    if document.is_repaired:
        document.close()
        raise UnsupportedDocument("This PDF requires repair. Export a fresh PDF before uploading.")
    for page in document:
        if max(page.rect.width, page.rect.height) > 3000 or min(page.rect.width, page.rect.height) < 50:
            document.close()
            raise UnsupportedDocument("This PDF uses unsupported page dimensions.")
    return document


def add_watermark(source: bytes, settings: WatermarkSettings) -> bytes:
    with open_pdf(source) as document:
        for page in document:
            # Normalize page rotation while preserving its visual appearance.
            page.remove_rotation()
            rect = page.rect
            margin = 24
            font = pymupdf.Font("helv")
            width = font.text_length(settings.text, fontsize=settings.font_size)
            height = settings.font_size * (font.ascender - font.descender)
            angle = math.radians(settings.rotation)
            box_width = abs(width * math.cos(angle)) + abs(height * math.sin(angle))
            box_height = abs(width * math.sin(angle)) + abs(height * math.cos(angle))
            scale = min(1, (rect.width - margin * 2) / max(box_width, 1), (rect.height - margin * 2) / max(box_height, 1))
            size = settings.font_size * scale
            width = font.text_length(settings.text, fontsize=size)
            box_height *= scale
            cy = rect.height / 2
            if settings.position == "top":
                cy = margin + box_height / 2
            elif settings.position == "bottom":
                cy = rect.height - margin - box_height / 2
            center = pymupdf.Point(rect.width / 2, cy)
            baseline = pymupdf.Point(center.x - width / 2, center.y + size * (font.ascender + font.descender) / 2)
            color = tuple(int(settings.color[index:index + 2], 16) / 255 for index in (1, 3, 5))
            page.insert_text(
                baseline, settings.text, fontname="helv", fontsize=size, color=color,
                fill_opacity=settings.opacity, stroke_opacity=settings.opacity,
                morph=(center, pymupdf.Matrix(settings.rotation)), overlay=True,
            )
        return document.tobytes(garbage=3, deflate=True)


def preview_pages(data: bytes):
    with open_pdf(data) as document:
        for index, page in enumerate(document):
            scale = min(1.25, 1100 / max(page.rect.width, page.rect.height))
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            yield index, pixmap.tobytes("png")
