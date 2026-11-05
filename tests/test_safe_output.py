"""Protect user edits and make stdout usable in Unix pipelines."""
from pathlib import Path

import fitz
import pytest

from pdfmd import Options, pdf_to_markdown
from pdfmd.cli import main


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "documento.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Monto total: $1.234.567. IVA: 19%. Articulo 31.")
        doc.save(path)
    return path


def test_cli_preserves_existing_markdown(pdf, capsys):
    out = pdf.with_suffix(".md")
    out.write_text("Correcciones manuales", encoding="utf-8")
    assert main([str(pdf), "--no-progress"]) == 1
    assert out.read_text() == "Correcciones manuales"
    assert "overwrite" in capsys.readouterr().err.lower()


def test_api_preserves_existing_markdown(pdf):
    out = pdf.with_suffix(".md")
    out.write_text("Notas", encoding="utf-8")
    with pytest.raises(FileExistsError):
        pdf_to_markdown(str(pdf), str(out), Options())
    assert out.read_text() == "Notas"


def test_cli_can_explicitly_overwrite(pdf):
    out = pdf.with_suffix(".md")
    out.write_text("Notas", encoding="utf-8")
    assert main([str(pdf), "--overwrite", "--no-progress"]) == 0
    assert "1.234.567" in out.read_text()


def test_stdout_contains_only_markdown(pdf, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main([str(pdf), "-o", "-", "--quiet", "--no-progress"]) == 0
    captured = capsys.readouterr()
    assert "Monto total" in captured.out
    assert captured.err == ""
    assert not (tmp_path / "-").exists()


@pytest.mark.parametrize("extra", [["--export-images"], ["--stats"]])
def test_stdout_rejects_incompatible_options(pdf, extra, capsys):
    assert main([str(pdf), "-o", "-", *extra]) == 1
    assert capsys.readouterr().out == ""


def test_stdout_rejects_multiple_inputs(pdf, capsys):
    assert main([str(pdf), str(pdf), "-o", "-"]) == 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_never_replaces_source_pdf(pdf, tmp_path, alias):
    original = pdf.read_bytes()
    target = pdf
    if alias == "symlink":
        target = tmp_path / "alias.md"
        target.symlink_to(pdf)
    elif alias == "hardlink":
        target = tmp_path / "alias.md"
        target.hardlink_to(pdf)
    assert main([str(pdf), "-o", str(target), "--overwrite", "--quiet"]) == 1
    assert pdf.read_bytes() == original


def test_quiet_still_reports_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.pdf"), "--quiet"]) == 1
    assert "not found" in capsys.readouterr().err


def test_existing_image_assets_are_preserved(pdf):
    assets = pdf.parent / "documento_assets"
    assets.mkdir()
    image = assets / "img_001_01.png"
    image.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        pdf_to_markdown(str(pdf), str(pdf.with_suffix(".md")), Options(export_images=True))
    assert image.read_bytes() == b"original"
    assert not pdf.with_suffix(".md").exists()


def test_stdout_ignores_directory_named_dash(pdf, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "-").mkdir()
    assert main([str(pdf), "-o", "-", "--quiet"]) == 0
    assert "Monto total" in capsys.readouterr().out
    assert list((tmp_path / "-").iterdir()) == []


def test_batch_rejects_duplicate_output_names_even_with_overwrite(tmp_path, capsys):
    inputs = []
    for name, text in [("a", "Alpha document"), ("b", "Beta document")]:
        folder = tmp_path / name; folder.mkdir()
        pdf = folder / "same.pdf"
        with fitz.open() as doc:
            page = doc.new_page(); page.insert_text((72,72), text); doc.save(pdf)
        inputs.append(str(pdf))
    output = tmp_path / "out"
    assert main([*inputs, "-o", str(output), "--overwrite", "--quiet"]) == 1
    assert "same.md" in capsys.readouterr().err
    assert not (output / "same.md").exists()


def test_encrypted_word_in_filename_does_not_trigger_password_prompt(pdf, capsys):
    output = pdf.parent / "encrypted-notes.md"
    output.write_text("Existing notes")
    assert main([str(pdf), "-o", str(output), "--quiet"]) == 1
    error = capsys.readouterr().err
    assert "overwrite" in error
    assert "password protected" not in error


def test_quiet_reports_password_required_for_noninteractive_pdf(tmp_path, capsys, monkeypatch):
    pdf = tmp_path / "protected.pdf"
    with fitz.open() as doc:
        page = doc.new_page(); page.insert_text((72,72), "Protected text")
        doc.save(pdf, encryption=fitz.PDF_ENCRYPT_AES_256,
                 owner_pw="owner-password", user_pw="user-password")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main([str(pdf), "--quiet"]) == 1
    assert "password" in capsys.readouterr().err.lower()


def test_image_assets_created_during_conversion_are_not_overwritten(pdf):
    with fitz.open(pdf) as doc:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0,0,20,20), False)
        pix.clear_with(255)
        doc[0].insert_image(fitz.Rect(72,120,150,200), pixmap=pix)
        doc.saveIncr()
    assets = pdf.parent / "documento_assets"
    image = assets / "img_001_01.png"
    def concurrent_conversion(done, total):
        if done == 80:
            assets.mkdir()
            image.write_bytes(b"another conversion's image")
    with pytest.raises(FileExistsError):
        pdf_to_markdown(str(pdf), str(pdf.with_suffix(".md")), Options(export_images=True),
                        progress_cb=concurrent_conversion)
    assert image.read_bytes() == b"another conversion's image"
    assert not pdf.with_suffix(".md").exists()
