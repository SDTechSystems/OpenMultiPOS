# OpenMultiPOS

Espacio administrativo autohospedado sobre **ERPNext + Frappe + X POS**, orientado a gestionar dos negocios: ventas, inventario, compras, finanzas, clientes, equipo y recibos internos.

**La administración se abre en `/omp`**, con una cuenta administrativa. Menú lateral, selector de negocio, perfiles privados, productos con SKU automático y entradas de inventario, cesta de ambos negocios, datos de recibo configurables, manual con capturas y guías por sección. Español latinoamericano, COP y America/Bogota por defecto; configuración editable. El backend funciona en WSL y el navegador/equipos en Windows.

Las operaciones usan documentos, stock y contabilidad nativos; una cesta conjunta crea una factura por negocio y un recibo interno. Solo se personalizan la impresora y el lector existentes. La impresión ya fue confirmada por el propietario; se conserva el preset. DIAN y operación sin conexión siguen desactivadas. La recuperación local incluye respaldo diario, ensayo aislado y conciliación; las APIs anteriores de X POS quedan cerradas salvo tres adaptadores autorizados. Revisa configuración privada y resultados antes de cargar datos reales.

- [Manual visual de administración](docs/manual.md)
- [Configuración y contratos del espacio de trabajo](docs/workspace.md)
- [Funcionalidades F01-F28](docs/features.md) · [Roadmap e issues](docs/roadmap.md)
- [Arquitectura](docs/architecture.md) · [Auditoría y resultados](docs/audit-report.md)
- [Impresora y lector existentes](docs/hardware-jaltech.md)
- [Caja de cajero: uso y recuperación](docs/cashier-ui.md)
- [Servicios locales y Windows/WSL](docs/local-services.md)
- [Respaldo, reinicio y restauración](docs/recovery.md) · [Política de APIs anteriores](docs/upstream-api-review.md)
- [Ramas, PRs y privacidad](docs/github-workflow.md)

## Probar ahora: demo local

Requisito: Python **3.14** con pip/venv. No requiere ERPNext, impresora, cuentas bancarias ni DIAN. Linux/macOS:

```bash
git clone https://github.com/SDTechSystems/OpenMultiPOS.git
cd OpenMultiPOS
git switch codex/business-workspace
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

## Impresora Windows existente y componentes históricos

Perfiles JSON en `open_multi_pos/profiles/printers.json`: Jaltech de referencia (57 mm, 384 puntos), genérica 58 mm y genérica 80 mm. El layout usa ancho útil, DPI y capacidades; no requiere que la impresora sea Jaltech. La personalización actual solo usa el preset del equipo existente; no se añade otro modelo.

El perfil separa **rollo físico**, **página lógica del controlador** y **ancho útil**. En la cola Windows ensayada, el rollo de 57/58 mm se anuncia como página de 48 mm; el perfil POS-58 usa 48 mm de página y 44 mm de contenido con 2 mm de margen por lado. Así no se centra un PDF de 57 mm sobre una página de 48 mm que recortaría el extremo derecho. Otros controladores requieren su propio perfil calibrado.

La vista previa y el botón de la demo usan navegador/driver. El documento calcula altura según contenido, pero el diálogo físico puede imponer formularios de 210/297/3276 mm. Un PDF corto **no garantiza** que ese controlador avance solo el contenido. Para longitud variable se añadió un diagnóstico local Windows/ESC-POS: raster monocromático, ancho validado, bloques continuos y pequeño avance final, sin corte automático ni cajón. El propietario confirmó una salida compacta (~9 cm de contenido), centrada y legible usando esa vía. No es una certificación de todos los modelos.

La vía nativa es un **CLI local explícito**; todavía no está conectada al botón web ni expuesta como endpoint/puente de impresión. No se requiere como paso de la operación actual. Desde un checkout con Node/Playwright, Chrome y Python Windows disponibles:

```powershell
node scripts/render-receipt-raster.cjs 'http://127.0.0.1:8765/api/receipt?id=ID_DEMO&profile=jaltech-jal58m' test-results/receipt-native
python -m open_multi_pos.windows_print test-results/receipt-native.pbm --printer 'NOMBRE_DE_COLA_LOCAL' --max-dots 384 --raster-command gs-v-0
```

El helper valida PBM/dimensiones y envía a una cola existente, sin instalar drivers ni cambiar políticas/defaults. Devuelve `submitted` con ID de trabajo; no reintenta automáticamente ni confirma papel. Reimpresión se decide después de revisar el estado. GS v 0 es un comando heredado, no universal. Los ensayos, limitaciones y referencias están en [hardware-jaltech.md](docs/hardware-jaltech.md) y [receipt-specification.md](docs/receipt-specification.md).

El diagnóstico del lector permite activar **«Lector USB configurado con teclado US»** cuando el teclado de Windows usa otra distribución. Interpreta códigos físicos solo en los campos de escaneo/búsqueda; no reemplaza texto de URLs ya leídas ni cambia el idioma del equipo. Usar desactivado para tecleo normal local; el valor esperado opcional compara la lectura exacta. Una lectura como `httpsÑ--...` evidencia un posible desajuste de distribución, no un QR comercial válido.

## App Frappe

La app añade marcas, usuarios, terminales y [caja nativa en línea](docs/native-checkout.md). Empresa, almacén y POS Profile deben coincidir. El servicio cotiza con ERPNext y envía Sales Invoice con stock/contabilidad inmediatos, pagos mixtos, apertura/cierre y snapshot de recibo. El cajero mantiene permisos nativos y escrituras limitadas al servicio. Los adaptadores protegen lectura/impresión; 14 operaciones de factura X POS siguen bloqueadas y su pantalla no usa todavía el nuevo checkout. Ver [seguridad de APIs](docs/xpos-api-security.md), [desarrollo](docs/development.md) y [despliegue](docs/deployment.md).

SHAs revisados e instalados en [upstream.lock.json](upstream.lock.json): Frappe 16.52.0, ERPNext 16.51.1 y X POS 2.12.0. Instalación, migración y pruebas locales aprobadas sin modificar core. Chrome Windows alcanza el backend WSL; web y worker funcionan como servicios de usuario. Abrir `/omp_pos` con un cajero y terminal configurados según [la guía](docs/cashier-ui.md). Mantener datos ficticios hasta revisar el resto de APIs y la recuperación operativa.

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
python scripts/check-receipt-pdfs.py
```

Para Chromium administrado por Playwright: `npx playwright install chromium` y definir `OMP_BROWSER_CHANNEL=chromium`. Capturas y resultados van a `test-results/`, ignorado por Git. GitHub Actions ejecuta privacidad, Python, navegador y un sitio Bench desechable. Los 48 tests sin framework incluyen contratos con mocks; la suite Bench se ejecuta por separado según [development.md](docs/development.md). Ver resultados reales en [audit-report.md](docs/audit-report.md).

## Alcance fiscal, marcas y licencia

Recibos internos claramente identificados. DIAN permanece desactivada; no hay CUFE ni emisión electrónica. [Contrato futuro](docs/fiscal-future.md).

GPL-3.0-only para código original. [Atribuciones](THIRD_PARTY_NOTICES.md), [contribución](CONTRIBUTING.md), [seguridad](SECURITY.md). Sin logotipos comerciales ni datos reales versionados; cada instalación aporta su propia configuración privada.
