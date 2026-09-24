"""The Streamlit page (design D2). The only module that imports Streamlit.

It renders what `view.py` computes and calls `service.analyze_document` once per document.
No prompt text, no model request and no business rule lives here.
"""

import base64
import tempfile
from decimal import Decimal
from pathlib import Path

import anthropic
import streamlit as st

from invoice_extractor.client import Parsed
from invoice_extractor.config import ConfigError
from invoice_extractor.extraction import IMAGE_SUFFIXES, UnsupportedInputError
from invoice_extractor.prompts import PROMPTS_DIR, PromptNotFoundError, load_prompt
from invoice_extractor.ui import service, view
from invoice_extractor.ui.view import ResultRow


def money(amount) -> str:
    """A cost, escaped for markdown: Streamlit reads a pair of dollar signs as LaTeX."""
    return view.format_usd(amount).replace("$", r"\$")


ACCEPTED_SUFFIXES = ["pdf", "jpg", "jpeg", "png"]
DEFAULT_CAP_USD = Decimal("1.00")
MAX_CAP_USD = 5.0

ABOUT = (
    "Proyecto de portfolio: extrae facturas argentinas (A, B, C y E) a objetos validados y mide "
    "su propia precisión y su costo por documento. Las métricas publicadas se miden sobre 30 "
    "documentos sintéticos. No valida CUIT ni CAE contra los registros de ARCA. "
    "Los archivos que subas se procesan localmente y no se guardan."
)


def _prompt_versions() -> list[str]:
    # Oldest first, so the page's default is the baseline the CLI also defaults to.
    versions = sorted((p.stem for p in PROMPTS_DIR.glob("v*.md")), key=lambda v: int(v[1:]))
    return versions or ["v1"]


def _sidebar(config) -> tuple[str, str, Decimal]:
    with st.sidebar:
        st.header("Configuración")
        model = st.selectbox("Modelo", service.available_models(config))
        prompt_version = st.selectbox("Prompt", _prompt_versions())
        cap = st.slider(
            "Tope de gasto de la sesión (USD)",
            min_value=0.10,
            max_value=MAX_CAP_USD,
            value=float(DEFAULT_CAP_USD),
            step=0.10,
            help="No se puede desactivar. Se controla antes de cada documento.",
        )
        st.caption(r"Costo estimado por factura: ~\$0.04 con Sonnet 5, ~\$0.01 con Haiku 4.5.")
        st.divider()
        st.caption(ABOUT)
    return model, prompt_version, Decimal(str(cap))


def _store_upload(uploaded, directory: Path) -> Path:
    path = directory / uploaded.name
    path.write_bytes(uploaded.getvalue())
    return path


def _process(uploaded, *, client, prompt, spent: Decimal, cap: Decimal) -> tuple[ResultRow, bytes | None]:
    blocked = view.cap_check(spent, cap)
    if blocked:
        return view.not_processed_row(uploaded.name, blocked), None

    data = uploaded.getvalue()
    # Outside the repo, and gone as soon as the document is processed (design D5).
    with tempfile.TemporaryDirectory(prefix="invoice-ui-") as scratch:
        path = _store_upload(uploaded, Path(scratch))
        try:
            record = service.analyze_document(path, client=client, prompt=prompt)
        except UnsupportedInputError as exc:
            return view.not_processed_row(uploaded.name, str(exc)), data
    st.session_state.records[uploaded.name] = record
    return view.row_from_record(record), data


def _render_row(row: ResultRow) -> None:
    icon = "✅" if row.is_success else ("⏸️" if row.outcome == "not_processed" else "⚠️")
    columns = st.columns([3, 2, 2, 2, 2])
    columns[0].markdown(f"**{icon} {row.file_name}**")
    columns[1].markdown(row.label)
    columns[2].markdown(f"**{view.format_amount(row.total)}** {row.currency or ''}" if row.is_success else "—")
    columns[3].markdown(money(row.cost_usd) if row.outcome != "not_processed" else "—")
    columns[4].markdown(view.format_latency(row.latency_ms))


def _render_source(name: str, data: bytes | None) -> None:
    if data is None:
        st.caption("El documento no se conservó.")
        return
    if Path(name).suffix.lower() in IMAGE_SUFFIXES:
        st.image(data, width="stretch")
        return
    encoded = base64.b64encode(data).decode("ascii")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{encoded}" width="100%" height="520"></iframe>',
        unsafe_allow_html=True,
    )
    st.caption("Si el visor no carga, abrí el PDF desde tu carpeta: el navegador puede bloquear PDFs embebidos.")


def _render_invoice(invoice) -> None:
    left, right = st.columns(2)
    left.markdown(
        f"**Emisor**  \n{invoice.issuer.name}  \nCUIT {invoice.issuer.cuit}  \n{invoice.issuer.vat_condition}"
    )
    right.markdown(
        f"**Cliente**  \n{invoice.customer.name or '—'}  \nCUIT {invoice.customer.cuit or '—'}  \n"
        f"{invoice.customer.vat_condition}"
    )

    st.markdown(
        f"**Comprobante** {invoice.invoice_type} · Nº {invoice.point_of_sale}-{invoice.invoice_number} · "
        f"Fecha {invoice.issue_date} · Vto. pago {invoice.due_date or '—'}  \n"
        f"**CAE** {invoice.cae.number} (vence {invoice.cae.expiry_date})"
    )

    st.markdown("**Ítems**")
    st.dataframe(
        [
            {
                "Código": item.code or "—",
                "Descripción": item.description,
                "Cantidad": view.format_amount(item.quantity),
                "Precio": view.format_amount(item.unit_price),
                "Bonif.": view.format_amount(item.discount),
                "IVA %": item.vat_rate if item.vat_rate is not None else "—",
                "Importe": view.format_amount(item.line_amount),
            }
            for item in invoice.items
        ],
        hide_index=True,
        width="stretch",
    )

    if invoice.vat_breakdown:
        st.markdown("**Desglose de IVA**")
        st.dataframe(
            [{"Alícuota": f"{line.rate}%", "Importe": view.format_amount(line.amount)} for line in invoice.vat_breakdown],
            hide_index=True,
            width="stretch",
        )
    if invoice.other_taxes:
        st.markdown("**Otros tributos**")
        st.dataframe(
            [{"Concepto": tax.description, "Importe": view.format_amount(tax.amount)} for tax in invoice.other_taxes],
            hide_index=True,
            width="stretch",
        )

    totals = {
        "Neto": invoice.net_amount,
        "No gravado": invoice.non_taxed_amount,
        "Exento": invoice.exempt_amount,
        "IVA": invoice.vat_amount,
        "Total": invoice.total,
    }
    st.markdown(
        "**Totales**  \n"
        + "  \n".join(f"{label}: {view.format_amount(amount)} {invoice.currency}" for label, amount in totals.items())
    )
    if invoice.exchange_rate is not None:
        st.markdown(f"**Cotización** {view.format_amount(invoice.exchange_rate)}")


def _render_detail(row: ResultRow, data: bytes | None) -> None:
    with st.expander(f"{row.file_name} — {row.label}", expanded=False):
        if row.outcome == "not_processed":
            st.warning(row.detail)
            return

        st.caption(
            f"modelo {row.model_id} · tokens {row.input_tokens} in / {row.output_tokens} out · "
            f"stop {row.stop_reason} · intentos {row.attempts} · costo {money(row.cost_usd)} · "
            f"{view.format_latency(row.latency_ms)} · request {row.request_id or '—'}"
        )

        record = st.session_state.records.get(row.file_name)
        document, fields = st.columns([1, 1])
        with document:
            _render_source(row.file_name, data)
        with fields:
            if not row.is_success:
                st.error(f"{row.label}: {row.detail}")
            elif record is not None and (invoice := view.invoice_of(record)) is not None:
                _render_invoice(invoice)

        if record is not None and isinstance(record.call.outcome, Parsed):
            st.markdown("**JSON**")
            st.json(record.call.outcome.value.model_dump(mode="json"))


def main() -> None:
    st.set_page_config(page_title="Invoice extractor", page_icon="🧾", layout="wide")
    st.title("🧾 Extractor de facturas")
    st.caption("Subí una factura argentina (PDF, JPG o PNG) y mirá cómo la clasifica, qué extrae y cuánto costó.")

    st.session_state.setdefault("rows", [])
    st.session_state.setdefault("records", {})
    st.session_state.setdefault("sources", {})
    st.session_state.setdefault("spent", Decimal(0))
    st.session_state.setdefault("processed_files", set())

    try:
        config = service.load_extractor_config()
    except ConfigError as exc:
        st.error(str(exc))
        return

    model, prompt_version, cap = _sidebar(config)

    uploads = st.file_uploader(
        "Documentos", type=ACCEPTED_SUFFIXES, accept_multiple_files=True, label_visibility="collapsed"
    )
    pending = [u for u in uploads or [] if u.name not in st.session_state.processed_files]

    if pending and st.button(f"Procesar {len(pending)} documento(s)", type="primary"):
        try:
            client = service.build_client(config, model)
            prompt = load_prompt(prompt_version)
        except (ConfigError, PromptNotFoundError) as exc:
            st.error(str(exc))
            return

        progress = st.progress(0.0, text="Procesando…")
        for index, uploaded in enumerate(pending, start=1):
            progress.progress((index - 1) / len(pending), text=f"Procesando {uploaded.name}…")
            try:
                row, data = _process(
                    uploaded, client=client, prompt=prompt, spent=st.session_state.spent, cap=cap
                )
            except anthropic.AnthropicError as exc:
                # Auth, permissions, unknown model or an exhausted balance: every later call fails too.
                st.error(f"{type(exc).__name__}: {exc}")
                break
            st.session_state.rows.append(row)
            st.session_state.sources[uploaded.name] = data
            st.session_state.processed_files.add(uploaded.name)
            st.session_state.spent += row.cost_usd
        progress.empty()

    rows: list[ResultRow] = st.session_state.rows
    if not rows:
        st.info("Ningún documento procesado todavía.")
        return

    totals = view.session_totals(rows)
    metrics = st.columns(4)
    metrics[0].metric("Documentos", totals.processed)
    metrics[1].metric("Extraídas", totals.extracted)
    metrics[2].metric("Fallas", totals.failures)
    metrics[3].metric("Costo de la sesión", view.format_usd(totals.cost_usd))
    st.caption(
        f"Tokens: {totals.input_tokens} de entrada / {totals.output_tokens} de salida · "
        f"tope de la sesión {money(cap)}"
    )
    if view.cap_check(totals.cost_usd, cap):
        st.warning("Se alcanzó el tope de gasto de la sesión. Subilo en la barra lateral para seguir.")

    st.divider()
    header = st.columns([3, 2, 2, 2, 2])
    for column, title in zip(header, ("Archivo", "Resultado", "Total", "Costo", "Latencia")):
        column.markdown(f"**{title}**")
    for row in rows:
        _render_row(row)

    st.divider()
    st.subheader("Detalle")
    for row in rows:
        _render_detail(row, st.session_state.sources.get(row.file_name))


main()
