"""Install/remove only pdfmd's per-user launcher and Dolphin service menu."""
from __future__ import annotations

import argparse
import configparser
import os
from pathlib import Path
import re
import sys
from typing import Optional, Sequence


def _exec_command() -> str:
    # Desktop Entry general string unescaping precedes Exec argument unquoting.
    # A literal % must be doubled so KDE does not treat it as a field code.
    executable = sys.executable.replace("%", "%%")
    if "\n" in executable or "\r" in executable:
        raise ValueError("Interpreter path contains a newline")
    quoted = '"' + re.sub(r'([\\"`$])', r'\\\1', executable) + '"'
    return quoted.replace("\\", "\\\\") + " -m pdfmd.desktop %F"


def _entries(data: Path) -> dict:
    command = _exec_command()
    return {
        data / "applications/pdfmd.desktop": (
            "[Desktop Entry]\nType=Application\nName=PDF a Markdown\n"
            "Comment=Convertir PDF locales a Markdown\nIcon=application-pdf\n"
            f"Exec={command}\nTerminal=false\nCategories=Office;Utility;\n"
            "MimeType=application/pdf;\nX-Pdfmd-Managed=true\n"
        ),
        data / "kio/servicemenus/pdfmd.desktop": (
            "[Desktop Entry]\nType=Service\nMimeType=application/pdf;\n"
            "X-KDE-ServiceTypes=KonqPopupMenu/Plugin\nX-KDE-Protocols=file\n"
            "Actions=convert;\nX-Pdfmd-Managed=true\n\n"
            "[Desktop Action convert]\nName=Convertir a Markdown (español)\n"
            f"Icon=application-pdf\nExec={command}\n"
        ),
    }


def _managed(path: Path) -> bool:
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read(path, encoding="utf-8")
        return config.getboolean("Desktop Entry", "X-Pdfmd-Managed", fallback=False)
    except (OSError, ValueError, configparser.Error):
        return False


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Instalar integración KDE por usuario, sin sudo.")
    parser.add_argument("--remove", action="store_true", help="Quitar lanzador y menú de Dolphin.")
    args = parser.parse_args(argv)
    data = Path(os.environ.get("XDG_DATA_HOME", ""))
    if not data.is_absolute():
        data = Path.home() / ".local/share"
    try:
        entries = _entries(data)
        # Check every destination first; leave unrelated user entries intact.
        for path in entries:
            if path.is_symlink() or (path.exists() and not _managed(path)):
                raise FileExistsError(f"Se conserva un archivo ajeno a pdfmd: {path}")
        for path, content in entries.items():
            if args.remove:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                path.chmod(0o755)
            print(f"{'Retirado' if args.remove else 'Instalado'}: {path}")
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
