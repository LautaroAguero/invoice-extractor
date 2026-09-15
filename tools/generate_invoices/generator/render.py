"""Renders one `InvoiceParams` to a clean PDF with pyfepdf (design D2/D6/D8).

Isolated by design: this module is the only place that imports pyafipws.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# pyafipws.utils imports pysimplesoap, which still calls inspect.getargspec
# (removed in Python 3.11). SOAP is not used for rendering; this only lets it import.
if not hasattr(inspect, "getargspec"):
    inspect.getargspec = inspect.getfullargspec

from pyafipws.pyfepdf import FEPDF  # noqa: E402

from .params import InvoiceParams
from .reproducibility import pinned_creation_date

HERE = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = HERE / "templates"

# AFIP alicuota ids (pyfepdf's `ivas_ds`/IVA_IDS convention, from the spike).
IVA_IDS = {Decimal("0"): 3, Decimal("10.5"): 4, Decimal("21"): 5, Decimal("27"): 6}
CURRENCY_CODES = {"USD": "DOL", "EUR": "060"}


@dataclass
class RenderResult:
    pdf_path: Path
    pages: int


def load_template(fepdf: FEPDF, template_name: str) -> None:
    """Load a template CSV, dropping the pyafipws logo and localizing image paths
    (the spike's edits, design D4)."""
    fepdf.CargarFormato(str(TEMPLATES_DIR / template_name))
    kept = []
    for el in fepdf.elements:
        if el["name"] == "Logo":
            continue
        if el["type"] == "I" and el.get("text"):
            el["text"] = str(TEMPLATES_DIR / Path(el["text"]).name)
        kept.append(el)
    fepdf.elements = kept


def _yyyymmdd(d) -> str:
    return d.strftime("%Y%m%d")


def render_invoice(
    params: InvoiceParams,
    *,
    template_name: str,
    out_path: Path,
    lineas_max: int = 24,
    extra_tipos_fact: dict[tuple[int, ...], str] | None = None,
    blank_cae: bool = False,
) -> RenderResult:
    """Render a clean document PDF. Raises on any rendering error
    (`LanzarExcepciones = True`, spec: "Generation fails loudly").

    `extra_tipos_fact` and `blank_cae` exist only for the presupuesto negative
    (design D5): it is not a real AFIP comprobante, so its title comes from a
    patched `tipos_fact` entry and it prints no CAE.
    """
    fepdf = FEPDF()
    fepdf.LanzarExcepciones = True
    load_template(fepdf, template_name)
    fepdf.FmtCantidad = "0.2"
    fepdf.FmtPrecio = "0.2"
    if extra_tipos_fact:
        fepdf.tipos_fact = dict(FEPDF.tipos_fact)
        fepdf.tipos_fact.update(extra_tipos_fact)

    is_foreign = params.currency != "ARS"
    moneda_id = CURRENCY_CODES[params.currency] if is_foreign else ""
    moneda_ctz = str(params.exchange_rate) if is_foreign else "1"

    if params.customer is None:
        tipo_doc, nro_doc = 99, "0"
        nombre_cliente = domicilio_cliente = ""
    else:
        tipo_doc, nro_doc = 80, params.customer.cuit
        nombre_cliente = params.customer.name
        domicilio_cliente = params.customer.address

    net_by_rate: dict[Decimal, tuple[Decimal, Decimal]] = {}
    for it in params.items:
        if not it.vat_rate:
            continue
        base, amt = net_by_rate.get(it.vat_rate, (Decimal("0.00"), Decimal("0.00")))
        net_by_rate[it.vat_rate] = (base + it.line_amount, amt + it.vat_amount)

    fepdf.CrearFactura(
        concepto=params.concepto,
        tipo_doc=tipo_doc,
        nro_doc=nro_doc,
        tipo_cbte=params.tipo_cbte,
        punto_vta=params.punto_vta,
        cbte_nro=params.cbte_nro,
        imp_total=str(params.total),
        imp_tot_conc="0.00",
        imp_neto=str(params.net_amount),
        imp_iva=str(params.vat_amount),
        imp_trib="0.00",
        imp_op_ex="0.00",
        fecha_cbte=_yyyymmdd(params.issue_date),
        fecha_venc_pago=_yyyymmdd(params.due_date) if params.due_date else "",
        fecha_serv_desde=_yyyymmdd(params.issue_date),
        fecha_serv_hasta=_yyyymmdd(params.issue_date),
        moneda_id=moneda_id,
        moneda_ctz=moneda_ctz,
        cae="" if blank_cae else params.cae,
        fch_venc_cae="" if blank_cae else _yyyymmdd(params.cae_expiry),
        id_impositivo=params.customer_vat_condition_label,
        nombre_cliente=nombre_cliente,
        domicilio_cliente=domicilio_cliente,
        pais_dst_cmp=200,
        forma_pago="Transferencia 30 dias",
        idioma_cbte=1,
    )

    for it in params.items:
        fepdf.AgregarDetalleItem(
            u_mtx=None,
            cod_mtx=None,
            codigo=it.code,
            ds=it.description,
            qty=str(it.quantity),
            umed=7,
            precio=str(it.unit_price),
            bonif=str(it.discount),
            iva_id=IVA_IDS[it.vat_rate or Decimal("0")],
            imp_iva=str(it.vat_amount),
            importe=str(it.line_amount),
            despacho="",
        )
    for rate, (base, amount) in net_by_rate.items():
        fepdf.AgregarIva(IVA_IDS[rate], str(base), str(amount))

    issuer = params.issuer
    for k, v in {
        "EMPRESA": issuer.name,
        "MEMBRETE1": issuer.address,
        "MEMBRETE2": "",
        "CUIT": f"CUIT {issuer.cuit[:2]}-{issuer.cuit[2:10]}-{issuer.cuit[10]}",
        "IIBB": f"IIBB {issuer.cuit}",
        "IVA": "IVA Responsable Inscripto",
        "INICIO": "Inicio de Actividad: 01/03/2015",
    }.items():
        fepdf.AgregarDato(k, v)
    fepdf.CUIT = issuer.cuit

    fepdf.CrearPlantilla(papel="A4", orientacion="portrait")
    fepdf.ProcesarPlantilla(num_copias=1, lineas_max=lineas_max, qty_pos="izq")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    when = datetime(params.issue_date.year, params.issue_date.month, params.issue_date.day, 12, 0, 0)
    with pinned_creation_date(when):
        fepdf.GenerarPDF(archivo=str(out_path))

    import pdfplumber

    with pdfplumber.open(out_path) as pdf:
        pages = len(pdf.pages)

    return RenderResult(pdf_path=out_path, pages=pages)


def extract_text(pdf_path: Path) -> str:
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)
