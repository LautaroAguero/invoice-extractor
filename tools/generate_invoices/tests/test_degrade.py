from generator.degrade import degrade_pdf
from generator.params import generate_params
from generator.render import render_invoice


def test_degrading_same_pdf_twice_with_same_seed_gives_identical_pixels(tmp_path):
    p = generate_params(6001, tipo_cbte=1, n_items=2)
    pdf_path = tmp_path / "clean.pdf"
    render_invoice(p, template_name="qr_base.csv", out_path=pdf_path)

    pages1 = degrade_pdf(pdf_path, seed=6001)
    pages2 = degrade_pdf(pdf_path, seed=6001)

    assert len(pages1) == len(pages2) == 1
    assert pages1[0].tobytes() == pages2[0].tobytes()
    assert pages1[0].size == pages2[0].size


def test_different_seed_gives_different_pixels(tmp_path):
    p = generate_params(6002, tipo_cbte=1, n_items=2)
    pdf_path = tmp_path / "clean.pdf"
    render_invoice(p, template_name="qr_base.csv", out_path=pdf_path)

    pages1 = degrade_pdf(pdf_path, seed=6002)
    pages2 = degrade_pdf(pdf_path, seed=9999)

    assert pages1[0].tobytes() != pages2[0].tobytes()
