# OpenMultiPOS

POS libre y autohospedable, diseñado como extensión de **ERPNext + Frappe + X POS** para operar varias marcas, inventarios, caja y recibos con impresoras configurables.

**Estado: primer incremento de desarrollo.** Incluye una demo local funcional y el scaffold de la app Frappe. Las ventas de la demo son simuladas. El checkout productivo, la instalación conjunta Bench y el modo offline todavía requieren integración y pruebas.

- [Funcionalidades F01–F19](docs/features.md)
- [Plan por fases y backlog](docs/roadmap.md)
- [Matriz de requisitos y gaps](docs/requirements-matrix.md)
- [Arquitectura](docs/architecture.md) · [Auditoría y resultados](docs/audit-report.md)
- [Impresoras y ensayos físicos](docs/hardware-jaltech.md)

## Probar ahora: demo local

Requisito: Python **3.14** con pip/venv. No requiere ERPNext, impresora, cuentas bancarias ni DIAN. Linux/macOS:

```bash
git clone https://github.com/JSX2011/OpenMultiPOS.git
cd OpenMultiPOS
git switch codex/foundation-and-roadmap
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m open_multi_pos.demo.server
```

Windows PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m open_multi_pos.demo.server
```

Abrir [la demo local](http://127.0.0.1:8765). Escoger Taller Aurora o Nexo Digital → agregar/escanear producto → registrar efectivo/transferencia → completar venta demo → previsualizar recibo → seleccionar perfil 58/80 mm → abrir diálogo de impresión. Se usan exclusivamente datos ficticios y un símbolo genérico de marca.

El selector de usuario **simula permisos y no autentica**. El cajero demo solo ve artesanía; el administrador demo ve ambos negocios. No exponer el servidor en red ni usar datos reales. SQLite persiste en `~/.openmultipos-demo/demo.sqlite3`; para una sesión nueva usar una ruta nueva con `--db`.

```bash
python -m open_multi_pos.demo.server --port 8766 --db /tmp/otra-demo.sqlite3
```

La búsqueda acepta SKU o código exacto con Enter; `VEL-01` / `7700000000011` corresponde a una vela. El panel **Prueba tu lector** muestra código y terminador sin abrir enlaces ni enviarlos al servidor. No se detecta automáticamente el modelo de escáner.

La demo calcula importes ficticios con centavos enteros, registra pagos mixtos, controla stock por marca, rechaza reintentos con payload diferente y conserva recibos históricos. **No calcula impuestos, no confirma transferencias, no escribe contabilidad ni sincroniza con ERPNext.** La clave de reintento se conserva mientras la página está abierta; recargar durante un cobro incierto requiere consultar la BD, no repetirlo como otra venta.

## Impresoras independientes del fabricante

Perfiles JSON en `open_multi_pos/profiles/printers.json`: Jaltech de referencia (57 mm, 384 puntos), genérica 58 mm y genérica 80 mm. El layout usa ancho útil, DPI y capacidades; no requiere que la impresora sea Jaltech. Para otro modelo se añade/calibra su perfil y se prueba con el controlador instalado.

El adaptador actual produce HTML/vista previa y permite imprimir mediante navegador/driver. El recibo calcula una página corta según contenido (ejemplo de un artículo: ~9 cm), omite pagos en cero y evita el formulario largo automático. Abrir el diálogo no confirma salida física. No hay envío USB/ESC/POS directo ni corte automático. Los ensayos y límites se registran en [hardware-jaltech.md](docs/hardware-jaltech.md). `scripts/print-diagnostic.ps1` sirve para imprimir un raster ficticio usando una cola Windows existente, sin instalar drivers ni cambiar la impresora predeterminada.

## App Frappe

La app `open_multi_pos` añade `OMP Business Brand`, su lista de usuarios, restricciones de lectura y un endpoint autorizado de contexto. Empresa, almacén y POS Profile deben coincidir. No tiene endpoint de ventas productivas en este incremento. Ver [desarrollo e instalación candidata](docs/development.md) y [despliegue](docs/deployment.md).

SHAs candidatos revisados en [upstream.lock.json](upstream.lock.json): Frappe 16.52.0, ERPNext 16.51.1 y X POS 2.12.0. Son fuentes fijadas; no se afirma que el conjunto instalado haya superado pruebas.

## Validación

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
pip-audit --no-deps --disable-pip -r requirements-runtime.txt
```

Navegador (ejecuta ventas ficticias; usar BD desechable): Node >=24 y Chrome instalado, `npm ci --ignore-scripts`, iniciar demo, después `npm run test:ui`. Para incluir axe en Linux/macOS:

```bash
OMP_AXE_MODULE=@axe-core/playwright npm run test:ui
```

Para Chromium administrado por Playwright: `npx playwright install chromium` y definir `OMP_BROWSER_CHANNEL=chromium`. Capturas y resultados van a `test-results/`, ignorado por Git. GitHub Actions ejecuta Python y navegador; los tests de contrato Frappe usan mocks y no reemplazan Bench. Ver resultados reales en [audit-report.md](docs/audit-report.md).

## Alcance fiscal, marcas y licencia

Recibos internos claramente identificados. DIAN permanece desactivada; no hay CUFE ni emisión electrónica. [Contrato futuro](docs/fiscal-future.md).

GPL-3.0-only para código original. [Atribuciones](THIRD_PARTY_NOTICES.md), [contribución](CONTRIBUTING.md), [seguridad](SECURITY.md). Sin logotipos comerciales ni datos reales versionados; cada instalación aporta su propia configuración privada.
