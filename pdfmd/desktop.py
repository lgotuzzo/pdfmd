"""Desktop entry points: GUI launcher and safe conversion from Dolphin."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Optional, Sequence

from .cli import main as cli_main


def _show_message(message: str, *, error: bool = False) -> None:
    dialog = shutil.which("kdialog")
    if dialog and (sys.platform == "linux"):
        try:
            subprocess.run(
                [dialog, "--title", "PDF a Markdown", "--error" if error else "--msgbox", message],
                check=False,
            )
            return
        except OSError:
            pass
    sys.stderr.write(message + "\n")


def gui_main() -> int:
    try:
        from .app_gui import PdfMdApp
        from tkinter import TclError
        try:
            app = PdfMdApp()
        except TclError as exc:
            _show_message(f"No se pudo abrir la interfaz gráfica: {exc}", error=True)
            return 1
        app.mainloop()
        return 0
    except (ImportError, RuntimeError) as exc:
        _show_message(
            f"No se pudo abrir la interfaz: {exc}\nEn CachyOS instala Tk: sudo pacman -S tk",
            error=True,
        )
        return 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    paths = list(sys.argv[1:] if argv is None else argv)
    if not paths:
        return gui_main()
    # Resolve paths before passing '--': filenames beginning with '-' stay data.
    paths = [str(Path(path).absolute()) for path in paths]
    errors = io.StringIO()
    with contextlib.redirect_stderr(errors):
        result = cli_main(["--profile", "es", "--quiet", "--no-progress", "--", *paths])
    if result:
        _show_message(
            "No se pudieron convertir todos los PDF. Los Markdown existentes se conservan.\n\n"
            + errors.getvalue(), error=True,
        )
    else:
        _show_message(
            f"Convertidos {len(paths)} PDF. Los archivos .md están junto a los originales."
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
