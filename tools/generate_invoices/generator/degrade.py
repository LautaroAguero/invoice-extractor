"""Rasterize -> rotate -> noise -> blur (design D7), driven by one seeded RNG per case.

Parameters (rotation range, noise amplitude, blur radius) were chosen by eye on
the first render (task 5.1) so the text stays human-readable, then frozen here.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from pathlib import Path
from random import Random

import pypdfium2 as pdfium
from PIL import Image, ImageFilter

RASTER_DPI = 200
ROTATION_RANGE_DEGREES = (2.0, 5.0)
NOISE_AMPLITUDE = 28  # +/- per-pixel jitter on the grayscale page, frozen in task 5.1
BLUR_RADIUS = 0.7  # Gaussian blur radius, frozen in task 5.1
JPEG_QUALITY = 70


def rasterize_pdf(pdf_path: Path) -> list[Image.Image]:
    """One RGB image per page at `RASTER_DPI`.

    Closes the pdfium document explicitly: on Windows, an open pypdfium2 handle
    on the file blocks anyone else (e.g. a caller's `TemporaryDirectory` cleanup)
    from deleting it, even after this function returns (task 7.1).
    """
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        scale = RASTER_DPI / 72
        return [page.render(scale=scale).to_pil().convert("RGB") for page in pdf]
    finally:
        pdf.close()


def _rotate(img: Image.Image, rng: Random) -> Image.Image:
    angle = rng.uniform(*ROTATION_RANGE_DEGREES)
    if rng.random() < 0.5:
        angle = -angle
    return img.rotate(angle, expand=True, fillcolor=(255, 255, 255), resample=Image.BICUBIC)


def _add_noise(img: Image.Image, rng: Random) -> Image.Image:
    gray = img.convert("L")
    pixels = [
        max(0, min(255, p + rng.randint(-NOISE_AMPLITUDE, NOISE_AMPLITUDE)))
        for p in gray.get_flattened_data()
    ]
    noisy = Image.new("L", gray.size)
    noisy.putdata(pixels)
    return noisy


def _blur(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS))


def degrade_page(img: Image.Image, rng: Random) -> Image.Image:
    return _blur(_add_noise(_rotate(img, rng), rng))


def degrade_pdf(pdf_path: Path, seed: int) -> list[Image.Image]:
    """Degrade every page of `pdf_path`. Same seed -> identical pixels (task 5.1)."""
    rng = Random(seed)
    return [degrade_page(page, rng) for page in rasterize_pdf(pdf_path)]


def save_skewed_scan_pdf(pages: list[Image.Image], out_path: Path, *, when: datetime) -> None:
    """Pillow PDF, one image per page, no text layer at all (spec: "No text layer")."""
    ts = time.struct_time(when.timetuple())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(
        out_path,
        "PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=RASTER_DPI,
        creationDate=ts,
        modDate=ts,
    )


def save_image_input_jpeg(pages: list[Image.Image], out_path: Path) -> None:
    """Single-page JPEG at `JPEG_QUALITY` (design D7: JPG cases are single-page)."""
    if len(pages) != 1:
        raise ValueError(f"image_input degradation expects a single page, got {len(pages)}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].convert("RGB").save(out_path, "JPEG", quality=JPEG_QUALITY)


def degradation_manifest_entry(clean_pdf_path: Path, *, kind: str) -> dict:
    """The manifest's `degradation` object (spec: "Provenance"): the clean source
    hash plus every parameter used, regardless of the per-page random outcome."""
    digest = hashlib.sha256(clean_pdf_path.read_bytes()).hexdigest()
    entry = {
        "source_sha256": digest,
        "resolution_dpi": RASTER_DPI,
        "rotation_degrees_range": list(ROTATION_RANGE_DEGREES),
        "noise_amplitude": NOISE_AMPLITUDE,
        "blur_radius": BLUR_RADIUS,
    }
    if kind == "image_input":
        entry["jpeg_quality"] = JPEG_QUALITY
    return entry
