"""Spike: render one synthetic Factura A with pyafipws' pyfepdf from a plain dict.

Not the dataset generator yet: it proves the rendering path works on Python 3.14
and writes the values it rendered next to the PDF. Variation (types A/B/E,
layouts, multi-page, degradation) comes after the ground-truth format is decided.

This file uses GPL-3.0 code (pyafipws), so it is GPL-3.0 as well. It is not
imported by the extractor package.

Usage:
    .venv/Scripts/python spike_factura_a.py                 # Factura A
    .venv/Scripts/python spike_factura_a.py --tipo-cbte 3   # Nota de Crédito A (a negative)
"""

import argparse
import inspect
import json
from decimal import Decimal
from pathlib import Path

# pyafipws.utils imports pysimplesoap, which still calls inspect.getargspec
# (removed in Python 3.11). SOAP is not used for rendering; this only lets it import.
if not hasattr(inspect, "getargspec"):
    inspect.getargspec = inspect.getfullargspec

from pyafipws.pyfepdf import FEPDF  # noqa: E402

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "templates" / "factura.csv"
OUT_DIR = HERE / "out"

IVA_IDS = {Decimal("21"): 5, Decimal("10.5"): 4}  # AFIP alicuota ids
CENT = Decimal("0.01")
# Class A comprobante codes this spike can render; the file stem names the output.
TIPOS_CBTE = {1: "spike_factura_a", 2: "spike_nota_debito_a", 3: "spike_nota_credito_a"}


def cuit_with_check_digit(base10: str) -> str:
    """Append the mod-11 check digit. Some bases have none (digit would be 10)."""
    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    r = sum(int(d) * w for d, w in zip(base10, weights)) % 11
    dv = 0 if r == 0 else 11 - r
    if dv == 10:
        raise ValueError(f"CUIT base {base10} has no valid check digit")
    return base10 + str(dv)


def load_template(fepdf: FEPDF) -> None:
    fepdf.CargarFormato(str(TEMPLATE))
    kept = []
    for el in fepdf.elements:
        if el["name"] == "Logo":  # pyafipws branding: not part of an AFIP invoice
            continue
        if el["type"] == "I" and el.get("text"):
            el["text"] = str(HERE / "templates" / Path(el["text"]).name)
        kept.append(el)
    fepdf.elements = kept


invoice = {
    "tipo_cbte": 1,  # Factura A
    "punto_vta": 3,
    "cbte_nro": 1542,
    "fecha_cbte": "20260812",
    "fecha_venc_pago": "20260911",
    "issuer_name": "Tecnored Patagonia S.A.",
    "issuer_cuit": cuit_with_check_digit("3071234567"),
    "customer_cuit": cuit_with_check_digit("3068765431"),
    "customer_name": "Distribuidora Los Andes S.R.L.",
    "customer_address": "Av. San Martin 1234, Mendoza",
    "cae": "76321458963214",
    "fch_venc_cae": "20260822",
    "items": [
        {"code": "SRV-01", "desc": "Soporte tecnico mensual", "qty": Decimal("1"), "unit_price": Decimal("150000.00"), "iva": Decimal("21")},
        {"code": "HW-220", "desc": "Router dual band AX3000", "qty": Decimal("2"), "unit_price": Decimal("48500.00"), "iva": Decimal("21")},
        {"code": "LIB-07", "desc": "Manual de configuracion impreso", "qty": Decimal("3"), "unit_price": Decimal("12000.00"), "iva": Decimal("10.5")},
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tipo-cbte", type=int, choices=sorted(TIPOS_CBTE), default=1)
    args = parser.parse_args()
    invoice["tipo_cbte"] = args.tipo_cbte
    stem = TIPOS_CBTE[args.tipo_cbte]

    fepdf = FEPDF()
    # pyfepdf swallows exceptions by default and returns False, which would let a
    # broken PDF ship with a JSON that claims it is fine.
    fepdf.LanzarExcepciones = True
    load_template(fepdf)
    fepdf.FmtCantidad = "0.2"
    fepdf.FmtPrecio = "0.2"

    net_by_rate: dict[Decimal, Decimal] = {}
    for it in invoice["items"]:
        net = (it["qty"] * it["unit_price"]).quantize(CENT)
        net_by_rate[it["iva"]] = net_by_rate.get(it["iva"], Decimal("0")) + net
    iva_by_rate = {r: (n * r / 100).quantize(CENT) for r, n in net_by_rate.items()}
    imp_neto = sum(net_by_rate.values())
    imp_iva = sum(iva_by_rate.values())
    imp_total = imp_neto + imp_iva

    fepdf.CrearFactura(
        concepto=3,
        tipo_doc=80,
        nro_doc=invoice["customer_cuit"],
        tipo_cbte=invoice["tipo_cbte"],
        punto_vta=invoice["punto_vta"],
        cbte_nro=invoice["cbte_nro"],
        imp_total=str(imp_total),
        imp_tot_conc="0.00",
        imp_neto=str(imp_neto),
        imp_iva=str(imp_iva),
        imp_trib="0.00",
        imp_op_ex="0.00",
        fecha_cbte=invoice["fecha_cbte"],
        fecha_venc_pago=invoice["fecha_venc_pago"],
        fecha_serv_desde=invoice["fecha_cbte"],
        fecha_serv_hasta=invoice["fecha_cbte"],
        moneda_id="PES",
        moneda_ctz=1,
        cae=invoice["cae"],
        fch_venc_cae=invoice["fch_venc_cae"],
        id_impositivo="Responsable Inscripto",
        nombre_cliente=invoice["customer_name"],
        domicilio_cliente=invoice["customer_address"],
        pais_dst_cmp=200,
        forma_pago="Transferencia 30 dias",
        idioma_cbte=1,
    )

    for it in invoice["items"]:
        net = (it["qty"] * it["unit_price"]).quantize(CENT)
        fepdf.AgregarDetalleItem(
            u_mtx=None, cod_mtx=None, codigo=it["code"], ds=it["desc"],
            qty=str(it["qty"]), umed=7, precio=str(it["unit_price"]), bonif="0.00",
            iva_id=IVA_IDS[it["iva"]], imp_iva=str((net * it["iva"] / 100).quantize(CENT)),
            importe=str(net), despacho="",
        )
    for rate, net in net_by_rate.items():
        fepdf.AgregarIva(IVA_IDS[rate], str(net), str(iva_by_rate[rate]))

    issuer = invoice["issuer_cuit"]
    for k, v in {
        "EMPRESA": invoice["issuer_name"],
        "MEMBRETE1": "Belgrano 455, Neuquen",
        "MEMBRETE2": "Tel. 0299 444-1234",
        "CUIT": f"CUIT {issuer[:2]}-{issuer[2:10]}-{issuer[10]}",
        "IIBB": f"IIBB {issuer}",
        "IVA": "IVA Responsable Inscripto",
        "INICIO": "Inicio de Actividad: 01/03/2015",
    }.items():
        fepdf.AgregarDato(k, v)
    fepdf.CUIT = issuer

    fepdf.CrearPlantilla(papel="A4", orientacion="portrait")
    fepdf.ProcesarPlantilla(num_copias=1, lineas_max=24, qty_pos="izq")

    OUT_DIR.mkdir(exist_ok=True)
    pdf_path = OUT_DIR / f"{stem}.pdf"
    fepdf.GenerarPDF(archivo=str(pdf_path))

    rendered = {
        **invoice,
        "items": [
            {**i, "qty": str(i["qty"]), "unit_price": str(i["unit_price"]), "iva": str(i["iva"])}
            for i in invoice["items"]
        ],
        "imp_neto": str(imp_neto),
        "imp_iva": str(imp_iva),
        "imp_total": str(imp_total),
    }
    (OUT_DIR / f"{stem}.rendered.json").write_text(
        json.dumps(rendered, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"pdf: {pdf_path} ({pdf_path.stat().st_size} bytes)")
    print(f"neto {imp_neto} | iva {imp_iva} | total {imp_total}")


if __name__ == "__main__":
    main()
