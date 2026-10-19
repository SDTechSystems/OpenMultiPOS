# Informe de auditoría inicial

Fecha: 18/10/2026. Alcance: inspección estática de tres checkouts version-16 fijados en upstream.lock.json, repositorio inicial y validación del incremento propio. No es una certificación de seguridad ni una auditoría completa de upstream.

## Antes de los cambios

OpenMultiPOS partía de commit cbe3ca8, con README y LICENSE GPLv3. Sin app, CI, tests, instrucciones AGENTS, issues o PRs. Sin trabajo local previo que conservar. Acceso de escritura confirmado para JSX2011.

Entorno: Python 3.14.4, git y gh disponibles; Bench, MariaDB/Redis y Docker no disponibles. Python del sistema sin pip/ensurepip; herramientas de desarrollo aisladas en /tmp, sin modificar el Python del sistema.

## Hallazgos de fuentes

| ID | Severidad | Evidencia/reproducción pendiente | Consecuencia / mitigación |
| --- | --- | --- | --- |
| U01 | Alta | X POS pyproject Python >=3.10 vs Frappe >=3.14,<3.15; README Node >=24 | Fijar candidatos por SHA y usar Python 3.14/Node 24; instalación conjunta pendiente. |
| U02 | Crítica para despliegue | create_invoice retorna duplicado por local_id/warehouse antes de validar perfil; insert/save usan ignore_permissions | No conectar datos reales. Probar usuario ajeno contra IDs y perfiles, permisos de draft y stock; revisar todos los endpoints. Hallazgo estático, explotación no confirmada. |
| U03 | Alta | find_invoice_by_local_id es lectura previa a creación; test_invoice_retry usa mocks secuenciales | Un test de reintento no demuestra atomicidad. Exigir unicidad en BD, hash de payload y prueba concurrente. |
| U04 | Alta | get_receipt_context y mark_invoice_printed en print_formats.py no contienen check_permission local explícito | Revisar permisos efectivos del framework y llamadas directas entre perfiles; no anunciar aislamiento total. No se reproduce contra un sitio instalado. |
| U05 | Alta | Offline tiene colas, cache y tests; README desaconseja Electron productivo | Offline no habilitado en la base; pendientes tests de reconexión/stock y revisión de cache de autenticación. |
| U06 | Media | print() / printview pueden pedir diálogo sin confirmar papel | Separar venta de impresión; evitar marcar trabajo exitoso automáticamente. |
| U07 | Media | Fabricante declara ESC/POS y QR, no todos los subcomandos | Perfiles por capacidades y driver primero; corte manual y hardware pendiente. |

Las rutas exactas y enlaces están en [upstream.md](upstream.md). No se ejecutaron tests upstream, escaneo completo de sus dependencias ni pruebas Bench; no afirmar ausencia de vulnerabilidades.

## Validación del incremento

| Comprobación | Resultado | Alcance |
| --- | --- | --- |
| `python -m unittest discover -s tests -v` | PASÓ · 29 tests | Simulador SQLite/HTTP, dinero preciso, stock, acceso cruzado, snapshots, payload manipulado, reintentos y concurrencia; contratos Frappe con fake, no Bench. |
| `ruff check .` / `ruff format --check .` | PASÓ | Código Python propio. |
| `python -m build` + inspección wheel | PASÓ | sdist/wheel; assets HTML/JS, perfiles y DocTypes incluidos. |
| Browser smoke con Chrome/Playwright | PASÓ | Cobro mixto, recibo/QR, cambio de perfil, API 403 entre marcas, teclado básico, sin overflow a 390/768/1366 px y sin errores JS. |
| axe sobre UI móvil | PASÓ · 0 violaciones en reglas seleccionadas | WCAG 2A/AA, 2.1AA, 2.2AA automatizadas. No certifica conformidad ni sustituye lector de pantalla. |
| `pip-audit --no-deps --disable-pip -r requirements-runtime.txt` | PASÓ · sin vulnerabilidades conocidas | Solo qrcode 8.2, única dependencia runtime propia; no cubre Frappe/X POS/transitivas. |
| `npm audit` | PASÓ · 0 vulnerabilidades conocidas | Dependencias de pruebas de navegador, no ERPNext. |
| Impresora conectada / POS-58 / USB001 | PARCIAL | Propietario confirma salida y aporta foto; texto pequeño borroso. Ajustes de raster/layout preparados; segunda prueba bloqueada por política de scripts Windows. Modelo exacto no confirmado. |
| Lector conectado | PASÓ · lectura física básica | Propietario escaneó un código alfanumérico de 10 caracteres, capturado en ~70–80 ms y confirmado en pantalla. No se publica el código real. Modelo, terminador exacto y matriz 1D/QR aún pendientes. |
| Instalación y ventas ERPNext/X POS | NO EJECUTADO | Sin Bench/DB/Redis. No se ha probado stock, impuestos, permisos ni offline productivos. |

## Revisión propia y límites

Foco visible, labels nativos, estado aria-live y layout responsive revisados mediante captura real. La primera ejecución de axe exigió contexto explícito de Playwright; se corrigió el runner y se repitió con éxito. Detectado contrato `ptype` y retorno booleano en has_permission de Frappe v16; ajustado al código revisado y cubierto por test.

La demo es accesible por loopback, valida Host/origen/token para escrituras y no sirve rutas arbitrarias. Su selector de usuario no autentica: cualquier usuario local puede elegir administrador demo. No se expone en red ni procesa datos reales. No existe endpoint productivo de checkout, canal de impresión abierto ni conexión fiscal.

Pendientes antes de uso real: suite Bench, auditoría completa de APIs upstream, caja/cierres, unicidad productiva, permisos entre empresas, escáner físico, legibilidad/QR impreso, backup/restauración y offline. Logotipos comerciales y fotos no publicados.

## Corrección de longitud del ticket

El propietario detectó una vista previa de papel muy largo. Se encontró `@page size: ancho auto`, inválido para el descriptor CSS de tamaño; el controlador podía mantener su formulario largo. Se sustituyó por medición del contenido y dos longitudes finitas, con fallback corto, límite de paginación y texto compacto sin pagos cero/diagnósticos. Navegador: el recibo de prueba mide 89 mm; PDF con una página, MediaBox 162 × 252 pt. Se añadió regresión de altura/tamaño en el smoke de UI. Prueba física de la nueva versión pendiente. Las primeras ejecuciones CI Python/navegador del PR pasaron; verificar el último commit en GitHub antes de integrar.

## Alineación del recibo compacto

El propietario aclaró que no hubo fallo de impresión: la observación era la alineación del contenido en la vista previa. Se retiró la regla de impresión que anulaba el centrado. El bloque mantiene 48 mm útiles centrados sobre 57 mm de papel (4,5 mm por lado en el PDF), sin cambiar la altura compacta. La calibración física por controlador sigue pendiente.

## Impresión y entrada HID: corrección posterior a fotos de ensayo

Se identificó la causa que no resolvía el centrado previo: PDF 57 mm sobre driver de 48 mm (`58(48)`), con recorte derecho. Nuevo contrato de perfil distingue rollo, página lógica, área imprimible y margen; layout fijo consistente antes/durante print, tabla de ancho fijo y wrapping. El navegador aún puede imponer formularios de longitud fija; se documenta sin prometer que CSS controla el avance físico.

Helper CLI nativo Windows sin red/endpoint: raster PBM acotado, bloques ESC/POS y cola local explícita, sin corte/cajón, sin retry automático. Ensayo RAW trabajo 3, 384 × 711 puntos (~89 mm), propietario confirma «looks perfect» y foto muestra texto/columnas/márgenes correctos. No se sube foto ni controlador. Revisión: rechazar raster truncado/excesivo, aborto/cierre de spooler ante error y no confundir envío con impresión; API Win32 verificada en Windows, no solo mocks.

Validación adicional: **31 tests Python**; navegador/axe sin fallos; **seis PDFs** de 48/58/80 mm inspeccionados con pypdf. Casos cortos <130 mm, márgenes estables y casos de 50 artículos con todos los marcadores y el pie en 4/4/3 páginas. Renderer solo tolera una columna de redondeo extra si está totalmente blanca.

El lector leyó QR pero entregó puntuación equivocada (`Ñ`/`-`): probable distribución US frente a Windows español. Nuevo modo optativo interpreta KeyboardEvent.code, limitado a campos de lector/búsqueda, desactivado por defecto y con comparación exacta. No reemplaza URLs/códigos recibidos ni cambia idioma del equipo. Test reproduce las teclas con layout discrepante y obtiene URL exacta. Confirmación física se registra aparte.

Lectura QR física posterior con modo US: el propietario confirmó `https://example.com/atelier` exacta; captura inspeccionada con 27 caracteres y Enter (~215 ms). Se mejoró comparación opcional de referencia: refresca al editar, ignora espacios exteriores solo en el valor humano y muestra ambos textos/longitudes si difieren. No se modifica el payload escaneado.
