import pytest

from generator.negatives import NEGATIVE_KINDS, render_negative
from generator.params import generate_params
from generator.render import extract_text


@pytest.mark.parametrize("kind", list(NEGATIVE_KINDS))
def test_negative_ground_truth_is_a_failed_result_with_the_right_reason(tmp_path, kind):
    spec = NEGATIVE_KINDS[kind]
    p = generate_params(4000 + spec["tipo_cbte"], tipo_cbte=spec["tipo_cbte"], n_items=1)

    result = render_negative(kind, p, out_path=tmp_path / f"{kind}.pdf")

    assert result.render.pdf_path.exists()
    assert result.ground_truth["result"]["outcome"] == "failed"
    assert result.ground_truth["result"]["reason"] == spec["reason"]
    assert result.ground_truth["result"]["detail"]


@pytest.mark.parametrize("kind", list(NEGATIVE_KINDS))
def test_negative_prints_its_expected_title(tmp_path, kind):
    spec = NEGATIVE_KINDS[kind]
    p = generate_params(4000 + spec["tipo_cbte"], tipo_cbte=spec["tipo_cbte"], n_items=1)

    result = render_negative(kind, p, out_path=tmp_path / f"{kind}.pdf")
    text = extract_text(result.render.pdf_path)

    assert spec["title"] in text


def test_presupuesto_has_no_cae_in_text(tmp_path):
    p = generate_params(4099, tipo_cbte=99, n_items=1)
    result = render_negative("presupuesto", p, out_path=tmp_path / "presupuesto.pdf")
    text = extract_text(result.render.pdf_path)
    assert "C.A.E" not in text
