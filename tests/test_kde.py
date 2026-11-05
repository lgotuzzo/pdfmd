"""Exercise per-user KDE installation and conversion as Dolphin invokes it."""
import configparser
import importlib
import os
from pathlib import Path
import shlex
import subprocess
import sys

import fitz
import pytest


def kde():
    return importlib.import_module("pdfmd.kde")


def desktop():
    return importlib.import_module("pdfmd.desktop")


def test_install_and_remove_use_xdg_data_home(tmp_path, monkeypatch):
    data = tmp_path / "datos con espacios"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    assert kde().main([]) == 0
    launcher = data / "applications/pdfmd.desktop"
    menu = data / "kio/servicemenus/pdfmd.desktop"
    assert launcher.is_file() and menu.is_file()
    assert menu.stat().st_mode & 0o100
    config = configparser.ConfigParser(interpolation=None)
    config.read(menu)
    assert config["Desktop Entry"]["MimeType"] == "application/pdf;"
    command = shlex.split(config["Desktop Action convert"]["Exec"])
    assert command == [sys.executable, "-m", "pdfmd.desktop", "%F"]
    assert kde().main(["--remove"]) == 0
    assert not launcher.exists() and not menu.exists()


def test_install_does_not_replace_unmanaged_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = tmp_path / "applications/pdfmd.desktop"
    path.parent.mkdir(); path.write_text("My custom launcher")
    assert kde().main([]) == 1
    assert path.read_text() == "My custom launcher"
    assert not (tmp_path / "kio/servicemenus/pdfmd.desktop").exists()
    assert kde().main(["--remove"]) == 1
    assert path.read_text() == "My custom launcher"


def test_install_uses_absolute_interpreter_with_reserved_characters(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    interpreter = '/home/test user/100%/$tool/`name`/python'
    monkeypatch.setattr(sys, "executable", interpreter)
    assert kde().main([]) == 0
    config = configparser.ConfigParser(interpolation=None)
    config.read(tmp_path / "kio/servicemenus/pdfmd.desktop")
    raw = config["Desktop Action convert"]["Exec"]
    # Desktop Entry string escaping is processed before Exec quoting.
    value = raw.replace("\\\\", "\\")
    tokens = shlex.split(value)
    # shlex keeps \$ and \` in double quotes; these are Exec escapes, not shell expansion.
    assert tokens[0].replace("\\$", "$").replace("\\`", "`").replace("%%", "%") == interpreter
    assert tokens[-1] == "%F"


def test_dolphin_conversion_handles_spaces_and_preserves_existing_output(tmp_path, capsys):
    pdf = tmp_path / "apunte con espacios.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72,72), "Este es un documento digital con una cifra de 1.234.567 pesos.")
        doc.save(pdf)
    assert desktop().main([str(pdf)]) == 0
    md = pdf.with_suffix(".md")
    assert "1.234.567" in md.read_text()
    assert "<!-- pdfmd:page=1 -->" in md.read_text()
    md.write_text("Notas personales")
    assert desktop().main([str(pdf)]) == 1
    assert md.read_text() == "Notas personales"
    assert "overwrite" in capsys.readouterr().err


def test_desktop_module_runs_outside_repository(tmp_path):
    pdf = tmp_path / "-archivo.pdf"
    with fitz.open() as doc:
        page = doc.new_page(); page.insert_text((72,72), "Digital text to convert from Dolphin without a terminal.")
        doc.save(pdf)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run([sys.executable, "-m", "pdfmd.desktop", str(pdf)],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Digital text" in pdf.with_suffix(".md").read_text()


def test_gui_startup_error_is_reported_without_traceback(monkeypatch, capsys):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert desktop().gui_main() == 1
    error = capsys.readouterr().err
    assert "interfaz" in error
    assert "Traceback" not in error
