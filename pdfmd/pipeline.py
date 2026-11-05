"""End-to-end conversion pipeline for pdfmd.

Public API:
    pdf_to_markdown(input_pdf: str, output_md: str, options: Options,
                    progress_cb: callable|None = None, log_cb: callable|None = None,
                    pdf_password: str|None = None, debug_tables: bool = False)

Stages:
    1) Extract → PageText pages   (native or OCR depending on Options)
    2) Transform → clean/annotate pages (drop caps, header/footer removal, table detection)
    3) Render → Markdown
    4) Optional: export images to _assets/ and append simple references

Notes:
    - `progress_cb` receives (done, total) at a few milestones; GUI can map this
      to a determinate bar.
    - Image references use forward slashes in Markdown (portable across OSes),
      while all file I/O uses Path/os to be cross-platform safe.
    - Password handling is secure: never logged, never persisted, only used in-memory.
    - Table detection can be debugged with debug_tables=True flag.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, List, Dict
import os
import sys
import tempfile

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

from .models import Options
from .extract import extract_pages, _open_pdf_with_password
from .transform import transform_pages
from .render import render_document
from .utils import log as default_log


DefProgress = Optional[Callable[[int, int], None]]
DefLogger = Optional[Callable[[str], None]]


def _append_image_refs(md: str, page_to_relpaths: Dict[int, List[str]]) -> str:
    """Append image references to the end of the Markdown document.
    
    Args:
        md: Markdown content
        page_to_relpaths: Mapping of page_index → list of relative image paths
        
    Returns:
        Markdown with image references appended
    """
    if not page_to_relpaths:
        return md
    
    lines: List[str] = [md.rstrip(), ""]
    
    for pno in sorted(page_to_relpaths):
        paths = page_to_relpaths[pno]
        if not paths:
            continue
        lines.append(f"**Images from page {pno + 1}:**")
        for i, rel in enumerate(paths, start=1):
            lines.append(f"- ![p{pno + 1}-{i}]({rel})")
        lines.append("")
    
    return "\n".join(lines).rstrip() + "\n"


def _export_images(
    pdf_path: str,
    output_md: str,
    options: Options,
    log_cb: DefLogger = None,
    pdf_password: Optional[str] = None,
) -> Dict[int, List[str]]:
    """Export images to an _assets folder next to output_md and return relative paths.

    Returns a mapping: page_index → [relpath, ...].

    For password-protected PDFs, the password is used only to open the
    document in memory. It is never logged or persisted.
    
    Args:
        pdf_path: Path to input PDF
        output_md: Path to output Markdown file
        options: Conversion options
        log_cb: Optional logging callback
        pdf_password: Optional PDF password (ephemeral, in-memory only)
        
    Returns:
        Dictionary mapping page indices to lists of relative image paths
    """
    if not options.export_images:
        return {}
    
    if fitz is None:
        if log_cb:
            log_cb("[pipeline] PyMuPDF is not available; cannot export images.")
        return {}

    try:
        # Reuse the central password-aware open helper so behavior matches extract.py
        doc = _open_pdf_with_password(pdf_path, pdf_password)
    except Exception as e:
        if log_cb:
            log_cb(f"[pipeline] Could not export images: {e}")
        return {}

    try:
        out_path = Path(output_md)
        assets_dir = out_path.with_name(out_path.stem + "_assets")
        assets_dir.mkdir(parents=True, exist_ok=True)

        mapping: Dict[int, List[str]] = {}
        page_count = doc.page_count
        limit = page_count if not options.preview_only else min(3, page_count)

        for pno in range(limit):
            page = doc.load_page(pno)
            images = page.get_images(full=True)
            rels: List[str] = []
            
            for idx, img in enumerate(images, start=1):
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                except Exception as exc:
                    if log_cb:
                        log_cb(f"[pipeline] Skipping image xref={xref} on page {pno + 1}: {exc}")
                    continue
                
                # Convert any non-RGB/Gray colorspace (CMYK, ICC, etc.) to RGB.
                # PNG only supports RGB(A) and Gray(A), so anything else must
                # be converted before saving.
                if pix.colorspace and pix.colorspace.n > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                
                # Drop alpha channel if present — avoids issues with some
                # viewers and keeps file sizes smaller.
                if pix.alpha:
                    pix = fitz.Pixmap(pix, 0)  # 0 = drop alpha
                
                fname = assets_dir / f"img_{pno + 1:03d}_{idx:02d}.png"
                try:
                    pix.save(str(fname))
                except Exception as exc:
                    if log_cb:
                        log_cb(f"[pipeline] Could not save image p{pno + 1}-{idx}: {exc}")
                    continue
                
                # Markdown wants forward slashes for portability
                rel = assets_dir.name + "/" + fname.name
                rels.append(rel)
            
            if rels:
                mapping[pno] = rels
        
        if log_cb and mapping:
            log_cb(f"[pipeline] Exported images to folder: {assets_dir}")
        
        return mapping
    
    finally:
        doc.close()


def pdf_to_markdown(
    input_pdf: str,
    output_md: str,
    options: Options,
    progress_cb: DefProgress = None,
    log_cb: DefLogger = None,
    pdf_password: Optional[str] = None,
    debug_tables: bool = False,
) -> None:
    """Convert a PDF to Markdown using the full pdfmd pipeline.
    
    This is the main entry point for PDF to Markdown conversion. It orchestrates
    all stages: extraction, transformation, rendering, and optional image export.
    
    Args:
        input_pdf: Path to input PDF file
        output_md: Path where Markdown output will be written
        options: Conversion options (OCR mode, heading detection, etc.)
        progress_cb: Optional callback for progress updates: (done, total)
        log_cb: Optional callback for log messages
        pdf_password: Optional password for encrypted PDFs (ephemeral)
        debug_tables: Enable debug logging for table detection
        
    Raises:
        RuntimeError: If PyMuPDF is not installed
        ValueError: If PDF has no pages or is invalid
        Various exceptions from extraction, transformation, or rendering stages
        
    Side Effects:
        - Writes Markdown file to output_md
        - May create _assets/ folder if export_images is enabled
        - Calls progress_cb and log_cb if provided
        
    Security Notes:
        - pdf_password is never logged or persisted
        - All processing happens locally
        - Output files are written unencrypted
    """
    if log_cb is None:
        log_cb = default_log

    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is not installed. Install with: pip install pymupdf")

    to_stdout = output_md == "-"
    out_path = Path(output_md)
    if to_stdout and options.export_images:
        raise ValueError("Image export requires a Markdown file, not stdout.")
    if not to_stdout:
        source = Path(input_pdf)
        if out_path.resolve() == source.resolve() or (
            out_path.exists() and source.exists() and out_path.samefile(source)
        ):
            raise ValueError("Output must not replace the input PDF.")
        if out_path.is_symlink() or (out_path.exists() and not options.overwrite_existing):
            raise FileExistsError(f"Output already exists: {out_path}. Use --overwrite to replace it.")
        assets = out_path.with_name(out_path.stem + "_assets")
        if options.export_images and (assets.is_symlink() or (assets.exists() and not assets.is_dir())):
            raise ValueError(f"Image assets must be a real directory: {assets}")
        if options.export_images and assets.exists() and not options.overwrite_existing:
            raise FileExistsError(f"Image assets already exist: {assets}. Use --overwrite to replace them.")

    # --- Stage 1: Extract ---
    if log_cb:
        log_cb("[pipeline] Extracting text…")

    # Map page-level progress into the [0, 30] range of a 0 to 100 scale.
    def _stage1_progress(done_pages: int, total_pages: int) -> None:
        if progress_cb and total_pages > 0:
            pct = int(done_pages * 30 / total_pages)
            progress_cb(pct, 100)

    pages = extract_pages(
        input_pdf,
        options,
        progress_cb=_stage1_progress,
        pdf_password=pdf_password,
    )

    if not pages:
        raise ValueError("PDF extraction produced no pages")

    if progress_cb:
        progress_cb(30, 100)

    # --- Stage 2: Transform ---
    if log_cb:
        log_cb("[pipeline] Transforming pages…")
    
    pages_t, header, footer, body_sizes = transform_pages(
        pages, 
        options,
        debug_tables=debug_tables,
    )
    
    if log_cb and (header or footer):
        log_cb(f"[pipeline] Removed repeating edges → header={header!r}, footer={footer!r}")

    if progress_cb:
        progress_cb(60, 100)

    # --- Stage 3: Render ---
    if log_cb:
        log_cb("[pipeline] Rendering Markdown…")
    
    md = render_document(
        pages_t,
        options,
        body_sizes=body_sizes,
    )

    if progress_cb:
        progress_cb(80, 100)

    # --- Stage 4: Optional image export ---
    if options.export_images:
        if log_cb:
            log_cb("[pipeline] Exporting images…")
        
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".pdfmd-images-", dir=out_path.parent) as stage:
            staged_output = Path(stage) / out_path.name
            page_to_rel = _export_images(
                input_pdf, str(staged_output), options,
                log_cb=log_cb, pdf_password=pdf_password,
            )
            if page_to_rel:
                staged_assets = staged_output.with_name(staged_output.stem + "_assets")
                assets = out_path.with_name(out_path.stem + "_assets")
                if assets.is_symlink():
                    raise ValueError(f"Image assets must be a real directory: {assets}")
                if options.overwrite_existing and assets.is_dir():
                    for image in staged_assets.iterdir():
                        os.replace(image, assets / image.name)
                else:
                    if assets.exists():
                        raise FileExistsError(f"Image assets already exist: {assets}. Use --overwrite to replace them.")
                    try:
                        os.rename(staged_assets, assets)
                    except OSError as exc:
                        if assets.exists():
                            raise FileExistsError(f"Image assets already exist: {assets}") from exc
                        raise
                md = _append_image_refs(md, page_to_rel)

    if progress_cb:
        progress_cb(90, 100)

    # --- Write output ---
    if log_cb:
        log_cb("[pipeline] Writing output file…")
    
    try:
        if to_stdout:
            sys.stdout.write(md)
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # Publish only complete Markdown. Hard-link creation cannot clobber
            # a file another conversion created after the preflight check.
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=out_path.parent,
                    prefix=".pdfmd-", suffix=".tmp", delete=False,
                ) as temp:
                    temp_name = temp.name
                    temp.write(md)
                if options.overwrite_existing:
                    os.replace(temp_name, out_path)
                else:
                    os.link(temp_name, out_path)
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
    except Exception as e:
        if log_cb:
            log_cb(f"[pipeline] Error writing output: {e}")
        raise

    if progress_cb:
        progress_cb(100, 100)
    
    if log_cb:
        log_cb(f"[pipeline] Saved → {output_md}")


__all__ = [
    "pdf_to_markdown",
]