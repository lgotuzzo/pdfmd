"""Mixed documents must retain digital text and recognize scanned annexes."""
import io
import shutil

import fitz
import pytest
from PIL import Image, ImageDraw, ImageFont

from pdfmd import Options, pdf_to_markdown
from pdfmd import extract
from pdfmd.cli import main


def make_pdf(path, *, scan=True, small_image=False, scan_text="SCANNED ANNEX TOTAL 1234567"):
    doc = fitz.open()
    for n in range(3):
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(72, 72, 520, 500),
            f"Digital page {n+1}: Amount 1.234.567. " + "Original digital text remains exact. " * 5)
    page = doc.new_page()
    if scan:
        image = Image.new("RGB", (1200, 1500), "white")
        font = ImageFont.truetype("DejaVuSans.ttf", 48)
        ImageDraw.Draw(image).text((100, 250), scan_text, font=font, fill="black")
        buf = io.BytesIO(); image.save(buf, format="PNG")
        rect = fitz.Rect(72, 72, 92, 92) if small_image else page.rect
        page.insert_image(rect, stream=buf.getvalue())
    if small_image:
        page.insert_text((72, 130), "Short native note.")
    doc.save(path); doc.close()
    return path


def page_text(page):
    return " ".join(line.text() for block in page.blocks for line in block.lines)


@pytest.mark.skipif(not shutil.which("tesseract") or not extract._HAS_TESS,
                    reason="real Tesseract and pytesseract required")
def test_auto_recognizes_fourth_page_and_preserves_native_text(tmp_path):
    path = make_pdf(tmp_path / "mixed.pdf")
    pages = extract.extract_pages(str(path), Options(ocr_mode="auto", ocr_lang="eng"))
    assert "Amount 1.234.567" in page_text(pages[0])
    assert "SCANNED ANNEX TOTAL 1234567" in page_text(pages[3])


def test_scanned_page_without_ocr_fails_instead_of_succeeding_blank(tmp_path, monkeypatch):
    path = make_pdf(tmp_path / "scan.pdf")
    monkeypatch.setattr(extract, "_HAS_TESS", False)
    monkeypatch.setattr(extract, "_which", lambda name: None)
    with pytest.raises(RuntimeError, match="OCR"):
        extract.extract_pages(str(path), Options(ocr_mode="auto"))


def test_missing_ocr_language_is_diagnosed(tmp_path):
    if not shutil.which("tesseract") or not extract._HAS_TESS:
        pytest.skip("Tesseract required")
    path = make_pdf(tmp_path / "scan.pdf")
    with pytest.raises(RuntimeError, match="not_a_real_language"):
        extract.extract_pages(str(path), Options(ocr_mode="auto", ocr_lang="not_a_real_language"))


def test_native_pdf_needs_no_ocr_dependencies(tmp_path, monkeypatch):
    path = make_pdf(tmp_path / "digital.pdf", scan=False)
    monkeypatch.setattr(extract, "_HAS_TESS", False)
    monkeypatch.setattr(extract, "_which", lambda name: None)
    pages = extract.extract_pages(str(path), Options(ocr_mode="auto", ocr_lang="spa+eng"))
    assert "Amount 1.234.567" in page_text(pages[0])


def test_small_high_resolution_logo_does_not_trigger_ocr(tmp_path, monkeypatch):
    path = make_pdf(tmp_path / "logo.pdf", small_image=True)
    monkeypatch.setattr(extract, "_HAS_TESS", False)
    monkeypatch.setattr(extract, "_which", lambda name: None)
    pages = extract.extract_pages(str(path), Options(ocr_mode="auto"))
    assert page_text(pages[3]) == "Short native note."


def test_preview_does_not_ocr_later_scans(tmp_path, monkeypatch):
    path = make_pdf(tmp_path / "mixed.pdf")
    monkeypatch.setattr(extract, "_HAS_TESS", False)
    pages = extract.extract_pages(str(path), Options(ocr_mode="auto", preview_only=True))
    assert len(pages) == 3


def test_ocr_words_keep_spaces_and_paragraph_order():
    data = {"text": ["Hola", "mundo", "Segundo", "parrafo"],
            "block_num": [1,1,1,1], "par_num": [1,1,2,2], "line_num": [1,1,1,1],
            "left": [10,60,10,80], "top": [10,10,80,80], "height": [12]*4}
    page = extract.PageText.from_tesseract_data(data)
    lines = [line.text() for block in page.blocks for line in block.lines]
    assert lines == ["Hola mundo", "Segundo parrafo"]


def test_spanish_profile_and_page_references(tmp_path):
    path = make_pdf(tmp_path / "digital.pdf", scan=False)
    assert main([str(path), "--profile", "es", "--quiet", "--no-progress"]) == 0
    md = path.with_suffix(".md").read_text()
    for n in range(1,5):
        assert f"<!-- pdfmd:page={n} -->" in md
    assert md.count("\n---\n") == 3


def test_spanish_profile_allows_language_override(tmp_path):
    if not shutil.which("tesseract") or not extract._HAS_TESS:
        pytest.skip("Tesseract required")
    path = make_pdf(tmp_path / "scan.pdf")
    assert main([str(path), "--profile", "es", "--lang", "eng", "--quiet", "--no-progress"]) == 0
    assert "SCANNED ANNEX TOTAL 1234567" in path.with_suffix(".md").read_text()


def test_spanish_profile_recognizes_real_spanish_scan(tmp_path):
    if not shutil.which("tesseract") or not extract._HAS_TESS:
        pytest.skip("Tesseract required")
    if "spa" not in extract.pytesseract.get_languages(config=""):
        pytest.skip("Spanish language data required")
    path = make_pdf(tmp_path / "declaracion.pdf", scan_text="DECLARACIÓN TRIBUTARIA")
    assert main([str(path), "--profile", "es", "--quiet", "--no-progress"]) == 0
    assert "DECLARACIÓN TRIBUTARIA" in path.with_suffix(".md").read_text()
