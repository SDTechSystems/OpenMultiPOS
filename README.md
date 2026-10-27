# OpenMultiPOS

OpenMultiPOS es una aplicación autohospedada para administrar varios negocios desde un mismo espacio. Reúne ventas, inventario, compras, clientes, equipo y recibos internos sobre ERPNext, Frappe y X POS.

## Operación del negocio

El espacio administrativo se abre en `/omp` y la caja en `/omp_pos`. Cada usuario accede a los negocios y funciones que permite su cuenta.

- Organizar productos con SKU, existencias y almacenes por negocio.
- Registrar ventas y pagos mixtos, consultar recibos y realizar apertura y cierre de caja.
- Reunir productos de varios negocios en una cesta, con una factura por negocio y un recibo interno conjunto.
- Gestionar devoluciones e importar catálogos y existencias con revisión previa.
- Distribuir costos de compra mediante los comprobantes nativos de ERPNext.
- Consultar guías por sección y un manual visual de administración.

La configuración inicial usa español latinoamericano, pesos colombianos y la zona horaria de Bogotá. Las operaciones conservan los documentos, permisos, movimientos de inventario y contabilidad de ERPNext.

La aplicación está en desarrollo. La operación de caja requiere conexión con el servidor local. Los recibos son internos; la facturación electrónica DIAN no está habilitada. La impresión necesita un perfil calibrado para el equipo utilizado.

## Probar la demo

La demo permite recorrer una venta con negocios y productos ficticios, revisar el recibo y probar la entrada de un lector de códigos. Requiere Python 3.14 y no necesita una instalación de ERPNext.

```sh
git clone https://github.com/SDTechSystems/OpenMultiPOS.git
cd OpenMultiPOS
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m open_multi_pos.demo.server
```

En Windows PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m open_multi_pos.demo.server
```

Abrir `http://127.0.0.1:8765`. El selector de usuario simula permisos y no autentica. La demo guarda sus registros en `~/.openmultipos-demo/demo.sqlite3`; se puede elegir otra base con `--db` y otro puerto con `--port`.

La demo no confirma transferencias, calcula impuestos ni sincroniza con ERPNext. Debe ejecutarse localmente con datos ficticios. Durante un cobro incierto, consultar el registro antes de repetir la venta.

## Instalación y uso

La aplicación completa requiere un entorno Bench con las versiones de Frappe, ERPNext y X POS fijadas en [upstream.lock.json](upstream.lock.json). La configuración, migración y asignación de cuentas se describen en la [guía de despliegue](docs/deployment.md).

| Guía | Contenido |
| --- | --- |
| [Manual de administración](docs/manual.md) | Productos, ventas, compras y tareas habituales |
| [Caja](docs/cashier-ui.md) | Cobros, recibos y recuperación de operaciones |
| [Configuración del espacio](docs/workspace.md) | Negocios, perfiles y permisos |
| [Impresora y lector](docs/hardware-jaltech.md) | Perfiles de impresión y lectura HID |
| [Respaldo y restauración](docs/recovery.md) | Copias locales y recuperación |
| [Servicios locales](docs/local-services.md) | Backend WSL y acceso desde Windows |

La impresión desde el navegador usa el controlador de Windows. El diagnóstico ESC/POS es una herramienta local independiente y todavía no está conectado al botón de impresión web. La longitud del papel depende del perfil y del controlador.

## Desarrollo

```sh
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
```

Las pruebas de integración necesitan un sitio Bench separado. Las pruebas de navegador usan una base de demostración desechable. Consultar [desarrollo](docs/development.md), [arquitectura](docs/architecture.md) y [resultados y límites](docs/audit-report.md).

## Licencia y datos

El código original se distribuye bajo [GPL-3.0-only](LICENSE). Las dependencias conservan sus [licencias y atribuciones](THIRD_PARTY_NOTICES.md).

Cada instalación mantiene su configuración comercial privada. El repositorio utiliza datos ficticios y no debe contener credenciales, respaldos ni documentos reales de clientes. Consultar [seguridad](SECURITY.md) y [contribución](CONTRIBUTING.md).
