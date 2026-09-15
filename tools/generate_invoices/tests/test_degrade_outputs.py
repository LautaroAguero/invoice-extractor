from datetime import datetime

import pdfplumber

from generator.degrade import (
    degradation_manifest_entry,
    degrade_pdf,
    save_image_input_jpeg,
    save_skewed_scan_pdf,
)
from generator.params import generate_params
from generator.render import render_invoice


def test_skewed_scan_pdf_has_no_text_layer(tmp_path):
    p = generate_params(7001, tipo_cbte=1, n_items=2)
    clean_pdf = tmp_path / "clean.pdf"
    render_invoice(p, template_name="qr_base.csv", out_path=clean_pdf)

    pages = degrade_pdf(clean_pdf, seed=7001)
    skewed_path = tmp_path / "skewed.pdf"
    save_skewed_scan_pdf(pages, skewed_path, when=datetime(2026, 8, 12, 12, 0, 0))

    with pdfplumber.open(skewed_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert text == ""


def test_image_input_jpeg_is_single_page(tmp_path):
    p = generate_params(7002, tipo_cbte=1, n_items=1)
    clean_pdf = tmp_path / "clean.pdf"
    render_invoice(p, template_name="qr_base.csv", out_path=clean_pdf)

    pages = degrade_pdf(clean_pdf, seed=7002)
    jpeg_path = tmp_path / "scan.jpg"
    save_image_input_jpeg(pages, jpeg_path)

    assert jpeg_path.exists()
    from PIL import Image

    with Image.open(jpeg_path) as img:
        assert img.format == "JPEG"


def test_degradation_manifest_entry_carries_source_hash_and_parameters(tmp_path):
    p = generate_params(7003, tipo_cbte=1, n_items=1)
    clean_pdf = tmp_path / "clean.pdf"
    render_invoice(p, template_name="qr_base.csv", out_path=clean_pdf)

    entry = degradation_manifest_entry(clean_pdf, kind="skewed_scan")
    assert entry["source_sha256"]
    assert entry["resolution_dpi"] == 200
    assert entry["rotation_degrees_range"] == [2.0, 5.0]
    assert "noise_amplitude" in entry
    assert "blur_radius" in entry
    assert "jpeg_quality" not in entry

    jpeg_entry = degradation_manifest_entry(clean_pdf, kind="image_input")
    assert jpeg_entry["jpeg_quality"] == 70
