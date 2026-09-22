# invoice-extractor

Extrae facturas argentinas (A, B, C y E) a objetos estructurados y validados, y **mide su propia
confiabilidad y su costo por documento**. La medición es el producto: un extractor sin precisión por
campo ni costo por documento medidos no está terminado.

> Estado: etapas 1 a 3 completas (extracción, dataset sintético de 30 documentos, arnés de
> evaluación). La interfaz local ya funciona. Las etapas 4 y 5 (validación de negocio con reintentos
> correctivos, y CLI + README final con el log de iteraciones) están planificadas en `openspec/changes/`.
> Este README es provisorio: la etapa 5 lo reescribe con los resultados y el log.

## La interfaz local

Una página para una sola persona, en tu máquina: subís una factura y ves cómo la clasifica, qué
extrae y cuánto costó la llamada.

```bash
pip install -e .[ui]
```

```bash
python -m invoice_extractor.ui
```

Se abre en `http://localhost:8501`. Necesitás `ANTHROPIC_API_KEY` en el entorno o en un archivo
`.env` (copiá `.env.example`). Cada factura cuesta alrededor de USD 0,04 con Sonnet 5 y USD 0,01 con
Haiku 4.5.

Qué muestra:

- **Clasificación:** el tipo de comprobante (A, B, C o E), o una falla explícita con su motivo. Una
  falla nunca se muestra como una factura a medio llenar.
- **Costo y performance:** costo en USD calculado desde el `usage` real de la llamada, tokens de
  entrada y salida, latencia e intentos. Ningún número es una estimación.
- **Todos los campos:** emisor, cliente, fechas, tabla de ítems, desglose de IVA, totales y CAE, al
  lado del documento, más el JSON crudo.

En la barra lateral elegís el modelo (entre los que tienen precio en `config/extractor.toml`), la
versión del prompt y el **tope de gasto de la sesión**, que no se puede desactivar y se controla
antes de cada documento.

Formatos aceptados: PDF, JPG y PNG. Cualquier otro se rechaza antes de llamar al modelo. Los
archivos que subís se procesan en un directorio temporal fuera del repositorio y se borran ni bien
se procesan; nada se guarda.

## Desde la terminal

```bash
python -m invoice_extractor.extract_one ground_truth/A01.pdf
```

```bash
python -m invoice_extractor.evaluate --path a --spend-cap 3
```

El primero extrae un documento e imprime el resultado con su costo. El segundo corre el dataset
completo, guarda el run record en `runs/` y muestra el reporte de calidad. Para volver a renderizar
un reporte sin llamar al modelo: `python -m invoice_extractor.report_cli`.

## Tests

```bash
pytest
```

Pasan sin `ANTHROPIC_API_KEY` configurada y sin red: ningún test llama a la API.

## Cómo está organizado

| Carpeta | Qué hay |
|---|---|
| `src/invoice_extractor/` | El extractor: schema, cliente del modelo, extracción, evaluación e interfaz |
| `ground_truth/` | Los 30 documentos sintéticos con su ground truth y el manifest |
| `tools/generate_invoices/` | El generador del dataset (GPL-3.0, venv propio, nunca importado por el extractor) |
| `docs/prd/` | Un PRD por etapa, más el overview |
| `docs/` | Reglas de medición, reporte de calidad y análisis de fallas |
| `openspec/` | Specs vigentes y changes en curso |
| `runs/` | Run records de cada corrida de evaluación |

## Limitaciones conocidas

- El dataset medido es 100% sintético: la precisión sobre facturas reales no está medida.
- Con n=30, una corrida tiene un piso de ruido de unos ±9 puntos, y dos corridas no se distinguen
  por debajo de unos ±12,6 puntos.
- No valida CUIT ni CAE contra los registros de ARCA.
- La interfaz es local y para una sola persona. No hay despliegue ni autenticación.
