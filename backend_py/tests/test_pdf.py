import pymupdf
import pytest
from pydantic import ValidationError

from common.contracts import WatermarkSettings
from common.pdf import UnsupportedDocument, add_watermark, open_pdf, preview_pages


def sample_pdf():
    with pymupdf.open() as document:
        for rotation in (0, 90, 180, 270):
            page = document.new_page(width=420, height=595)
            page.insert_text((30, 70), "Original content must remain readable.", fontsize=12)
            page.set_rotation(rotation)
        return document.tobytes()


@pytest.mark.parametrize("position", ["center", "top", "bottom"])
@pytest.mark.parametrize("rotation", [-90, -45, 0, 45, 90])
def test_watermark_preserves_text_and_page_dimensions(position, rotation):
    original = sample_pdf()
    output = add_watermark(original, WatermarkSettings(text="DRAFT", position=position, rotation=rotation))
    with pymupdf.open(stream=original) as source, pymupdf.open(stream=output) as result:
        assert len(result) == len(source)
        for before, after in zip(source, result):
            assert before.rect == after.rect
            assert "Original content must remain readable." in after.get_text()
            assert "DRAFT" in after.get_text()
    with pymupdf.open(stream=original) as unchanged:
        assert all("DRAFT" not in page.get_text() for page in unchanged)


def test_rejects_invalid_and_encrypted_pdf():
    with pytest.raises(UnsupportedDocument):
        open_pdf(b"This is not a PDF")
    with pymupdf.open(stream=sample_pdf()) as document:
        encrypted = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    with pytest.raises(UnsupportedDocument, match="Password"):
        open_pdf(encrypted)


def test_preview_is_png_for_every_page():
    pages = list(preview_pages(sample_pdf()))
    assert len(pages) == 4
    assert all(data.startswith(b"\x89PNG") for _, data in pages)


@pytest.mark.parametrize("values", [{"opacity": 2}, {"text": ""}, {"text": "Hello\nWorld"}, {"color": "red"}, {"font_size": 999}, {"template_id": "unknown"}])
def test_invalid_settings_are_rejected(values):
    with pytest.raises(ValidationError):
        WatermarkSettings(**values)


def test_long_watermark_fits_small_page():
    output = add_watermark(sample_pdf(), WatermarkSettings(text="A" * 60, font_size=120, rotation=45))
    with pymupdf.open(stream=output) as result:
        assert "A" * 60 in result[0].get_text()
