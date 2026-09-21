import io
import json
import socket
from decimal import Decimal

import anthropic
import pytest

from builders import extracted, failed, make_entry, make_record, make_result, perfect_result, truth_payload, write_dataset
from fakes import RoutedSdk, make_message
from invoice_extractor import evaluate, report_cli
from invoice_extractor.client import ModelClient
from invoice_extractor.config import DEFAULT_CONFIG_PATH, load_config
from invoice_extractor.evaluation.run_record import make_run_id, read_run_record, write_run_record
from invoice_extractor.schema import Invoice

TRUTH = Invoice.model_validate(truth_payload("A01"))


def _perfect_text() -> str:
    return json.dumps({"result": {"outcome": "extracted", "invoice": truth_payload("A01")}})


def _not_an_invoice_text() -> str:
    return json.dumps({"result": {"outcome": "failed", "reason": "not_an_invoice", "detail": "n/a"}})


@pytest.fixture
def client():
    def answer(doc_id: str):
        return make_message(_not_an_invoice_text() if doc_id.startswith("N") else _perfect_text())

    return ModelClient(load_config(DEFAULT_CONFIG_PATH), RoutedSdk(answer))


@pytest.fixture
def datasets(tmp_path):
    synthetic, real = tmp_path / "ground_truth", tmp_path / "ground_truth_real"
    synthetic.mkdir(), real.mkdir()
    write_dataset(synthetic, [("D01", "extracted"), ("D02", "extracted"), ("N01", "negative")])
    write_dataset(real, [("R01", "extracted"), ("R02", "extracted")], source="real")
    return {"ground_truth": synthetic, "ground_truth_real": real}


def run_evaluate(argv, client, datasets, tmp_path):
    out = io.StringIO()
    code = evaluate.main(argv, client=client, out=out, runs_root=tmp_path / "runs", dataset_dirs=datasets)
    return code, out.getvalue()


def _written(tmp_path, pattern="*.json"):
    return sorted((tmp_path / "runs").glob(pattern))


# --- 11.1 evaluate ---------------------------------------------------------------------------------


def test_evaluate_writes_a_run_record_and_prints_the_report(client, datasets, tmp_path):
    code, output = run_evaluate([], client, datasets, tmp_path)

    assert code == evaluate.EXIT_OK
    (meta,) = _written(tmp_path)
    assert meta.with_suffix(".jsonl").is_file()
    assert "path_a" in meta.name
    assert f"run record: {meta}" in output
    assert "DOCUMENTS" in output and "Correct outcome" in output
    assert "REAL SET" not in output
    assert not (tmp_path / "runs" / "real").exists()
    record = read_run_record(tmp_path / "runs", meta.stem)
    assert record.aggregates.documents == 3 and record.config.complete


def test_the_real_set_is_written_only_under_runs_real(client, datasets, tmp_path):
    code, output = run_evaluate(["--dataset", "ground_truth_real"], client, datasets, tmp_path)

    assert code == evaluate.EXIT_OK
    assert [p.name for p in (tmp_path / "runs").iterdir()] == ["real"]  # nothing at the committed top level
    (meta,) = (tmp_path / "runs" / "real").glob("*.json")
    assert "REAL SET" in output and "NOT a headline number" in output
    assert "DOCUMENTS" not in output  # no headline over the real set


def test_path_b_makes_no_call_for_documents_it_cannot_read(client, datasets, tmp_path):
    code, _ = run_evaluate(["--path", "b"], client, datasets, tmp_path)  

    assert code == evaluate.EXIT_OK
    (meta,) = _written(tmp_path)
    assert "path_b" in meta.name
    assert client._sdk.requests == []
    record = read_run_record(tmp_path / "runs", meta.stem)
    assert all(r.no_call_reason == "unreadable_pdf" for r in record.results)  # the fake PDFs cannot be parsed


def test_path_compare_runs_both_paths_and_prints_the_comparison(client, datasets, tmp_path):
    code, output = run_evaluate(["--path", "compare"], client, datasets, tmp_path)

    assert code == evaluate.EXIT_OK
    assert sorted("path_a" in p.name for p in _written(tmp_path)) == [False, True]
    assert "INGESTION PATH COMPARISON" in output and "WINNER" in output
    assert output.count("DOCUMENTS") == 2  # one report per path


def test_the_spend_cap_saves_the_partial_record_and_exits_non_zero(client, datasets, tmp_path):
    code, output = run_evaluate(["--spend-cap", "0.03", "--max-concurrency", "1"], client, datasets, tmp_path)

    assert code == evaluate.EXIT_INCOMPLETE
    (meta,) = _written(tmp_path)
    record = read_run_record(tmp_path / "runs", meta.stem)
    assert record.config.complete is False and len(record.results) == 1
    assert "stopped by its spend cap" in output and "not reported as a result" in output
    assert "DOCUMENTS" not in output


def test_path_b_is_not_started_when_path_a_hits_its_cap(client, datasets, tmp_path):
    code, _ = run_evaluate(["--path", "compare", "--spend-cap", "0.03", "--max-concurrency", "1"], client, datasets, tmp_path)

    assert code == evaluate.EXIT_INCOMPLETE
    (meta,) = _written(tmp_path)
    assert "path_a" in meta.name and len(client._sdk.requests) == 1


@pytest.mark.parametrize(
    "argv",
    [["--spend-cap", "0"], ["--spend-cap", "-1"], ["--max-concurrency", "0"], ["--dataset", "ground_truth_real", "--path", "compare"], ["--prompt", "v9"]],
)
def test_bad_arguments_are_usage_errors_before_any_call(client, datasets, tmp_path, argv, capsys):
    code, _ = run_evaluate(argv, client, datasets, tmp_path)

    assert code == evaluate.EXIT_USAGE
    assert client._sdk.requests == []
    assert "error:" in capsys.readouterr().err and not _written(tmp_path)


def test_a_missing_api_key_is_a_usage_error(datasets, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(evaluate, "load_dotenv", lambda: None)  # never read a developer's real .env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = io.StringIO()

    code = evaluate.main([], out=out, runs_root=tmp_path / "runs", dataset_dirs=datasets)

    assert code == evaluate.EXIT_USAGE
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def test_a_configuration_error_from_the_api_is_reported_without_a_traceback(datasets, tmp_path, capsys):
    import httpx2

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.AuthenticationError("bad key", response=httpx2.Response(401, request=request), body=None)
    bad_client = ModelClient(load_config(DEFAULT_CONFIG_PATH), RoutedSdk(lambda doc: error))

    code, _ = run_evaluate([], bad_client, datasets, tmp_path)

    assert code == evaluate.EXIT_USAGE
    err = capsys.readouterr().err
    assert "AuthenticationError" in err and "Traceback" not in err


# --- 11.2 report_cli -------------------------------------------------------------------------------


def _save(tmp_path, results, subdir="runs", **config):
    record = make_record(results, **config)
    run_id = make_run_id(record.config)
    directory = tmp_path / "runs" if subdir == "runs" else tmp_path / "runs" / "real"
    write_run_record(directory, run_id, record)
    return run_id


def run_report(argv, tmp_path):
    out = io.StringIO()
    code = report_cli.main(argv, out=out, runs_root=tmp_path / "runs")
    return code, out.getvalue()


def _two_documents():
    return [perfect_result(make_entry("A01")), make_result(make_entry("A02"), failed("illegible"), TRUTH)]


@pytest.fixture
def no_network(monkeypatch):
    """Any attempt to build a client or open a connection fails the test."""

    def boom(*args, **kwargs):
        raise AssertionError("the report must not build a client or touch the network")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ModelClient, "from_config", classmethod(boom))
    monkeypatch.setattr(ModelClient, "call", boom)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)


def test_a_saved_run_re_renders_without_an_api_key_or_network(tmp_path, no_network):
    run_id = _save(tmp_path, _two_documents())

    code, output = run_report([run_id], tmp_path)

    assert code == report_cli.EXIT_OK
    assert "DOCUMENTS" in output and "1/2" in output
    assert "b8bc5d4" in output  # the report names the code that produced the run


def test_the_markdown_report_is_written_on_request(tmp_path, no_network):
    run_id = _save(tmp_path, _two_documents())
    target = tmp_path / "report.md"

    code, output = run_report([run_id, "--markdown", str(target)], tmp_path)

    assert code == report_cli.EXIT_OK and f"markdown written to {target}" in output
    assert target.read_text(encoding="utf-8").startswith("# Quality report")


def test_two_saved_runs_re_render_as_a_comparison(tmp_path, no_network):
    id_a = _save(tmp_path, _two_documents(), ingestion_path="a")
    id_b = _save(tmp_path, [perfect_result(make_entry("A01")), make_result(make_entry("A02", fmt="jpg"), None, TRUTH)], ingestion_path="b")
    target = tmp_path / "comparison.md"

    code, output = run_report([id_a, "--compare-with", id_b, "--markdown", str(target)], tmp_path)

    assert code == report_cli.EXIT_OK
    assert "INGESTION PATH COMPARISON" in output and "A02" in output
    assert "# Ingestion path comparison" in target.read_text(encoding="utf-8")


def test_a_real_set_run_is_read_from_runs_real(tmp_path, no_network):
    real = make_result(make_entry("real_01", source="real", fmt="jpg"), extracted(truth_payload("A01")), TRUTH)
    run_id = _save(tmp_path, [real], subdir="real")

    assert run_report([run_id], tmp_path)[0] == report_cli.EXIT_USAGE  # not under runs/
    code, output = run_report([run_id, "--dataset", "runs/real"], tmp_path)
    assert code == report_cli.EXIT_OK and "REAL SET" in output


def test_an_incomplete_run_is_refused_with_its_own_exit_code(tmp_path, no_network, capsys):
    run_id = _save(tmp_path, _two_documents(), complete=False)

    code, output = run_report([run_id], tmp_path)

    assert code == report_cli.EXIT_INCOMPLETE and output == ""
    assert "incomplete" in capsys.readouterr().err


def test_an_unknown_run_is_a_usage_error(tmp_path, capsys):
    code, _ = run_report(["nope"], tmp_path)
    assert code == report_cli.EXIT_USAGE and "no such run record" in capsys.readouterr().err


def test_a_run_whose_documents_were_edited_is_refused(tmp_path, capsys):
    run_id = _save(tmp_path, _two_documents())
    documents = tmp_path / "runs" / f"{run_id}.jsonl"
    documents.write_text(documents.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")

    code, _ = run_report([run_id], tmp_path)

    assert code == report_cli.EXIT_USAGE and "unreadable run record" in capsys.readouterr().err


def test_comparing_runs_over_different_documents_is_a_usage_error(tmp_path, capsys):
    id_a = _save(tmp_path, _two_documents(), ingestion_path="a")
    only_one = make_record([perfect_result(make_entry("A01"))], ingestion_path="b")
    write_run_record(tmp_path / "runs", "other", only_one)

    code, _ = run_report([id_a, "--compare-with", "other"], tmp_path)

    assert code == report_cli.EXIT_USAGE and "same documents" in capsys.readouterr().err


def test_spend_is_not_needed_to_render(tmp_path, no_network):
    run_id = _save(tmp_path, _two_documents(), spend_cap_usd=Decimal("0.01"))
    assert run_report([run_id], tmp_path)[0] == report_cli.EXIT_OK
