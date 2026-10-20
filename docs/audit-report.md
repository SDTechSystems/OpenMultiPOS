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

## Privacidad y flujo de publicación

Revisión de archivos versionados e historial de contenido: sin datos comerciales reales, fotos, bases locales ni credenciales detectados. Material de referencia privado permanece fuera del repositorio. Añadidos exclusiones, guard de publicación, hooks locales y trabajo CI previo a pruebas/artefactos; el guard detecta patrones y no sustituye revisión contextual. Validación local: **35 tests Python**, Ruff, formato Prettier y revisión de los **73 archivos** del índice correctos. Identidad de nuevos commits con alias y correo GitHub no-reply.

Protección remota de main verificada: PR obligatorio, comprobaciones requeridas, historial lineal, conversaciones resueltas, sin force-push ni eliminación y aplicación a administradores. Cuenta propietaria como único acceso de escritura; no se añaden colaboradores. Se documentan rama, PR, push y merge en `github-workflow.md`. El primer incremento permanece en PR de desarrollo, sin fusionar.

## Instalación real y permisos · 19/10/2026

Con autorización del propietario se instalaron herramientas y servicios en Ubuntu 26.04.1 WSL2. Python 3.14.4, Node 24.22.0 (archivo oficial con SHA256 verificado), Yarn 1.22.22, Bench 5.29.1, MariaDB 11.8.6 y Redis 8.0.5. MariaDB/Redis activos, habilitados al iniciar Ubuntu y escuchando en loopback. No se abrió firewall ni acceso remoto. Cuenta temporal de instalación eliminada después de crear el sitio; credenciales aleatorias y configuración del sitio fuera de Git y con permisos 600.

Instalación nueva de Frappe, ERPNext y X POS en los tres SHAs de `upstream.lock.json`, más OpenMultiPOS; ambos DocTypes migrados correctamente. Bench y las fuentes de ejecución residen en el filesystem Linux, separados del checkout Windows con espacios. El preparador verifica SHAs antes de instalar y no sobreescribe entornos existentes. CI usa imágenes MariaDB/Redis por digest; su resultado se vincula al commit de cada ejecución en PR #1.

Se detectó que Sales User no tiene lectura nativa de POS Profile. Se añadió OMP Cashier con permiso exclusivo de lectura, sin ampliar roles contables ni reemplazar permisos nativos. Hooks de lista y documento restringen sus perfiles por marca habilitada, autorización explícita y applicable_for_users. El contexto revalida además perfil habilitado y empresa actual del almacén. Los usuarios conservan User Permissions nativas por empresa.

| Evidencia local | Resultado | Límite |
| --- | --- | --- |
| Instalación y migrate | PASÓ | Frappe 16.52.0, ERPNext 16.51.1, X POS 2.12.0, OpenMultiPOS 0.1.0; sitio desechable. |
| Suite Bench/MariaDB | PASÓ · 9 pruebas | Dos marcas/empresas y dos cajeros, listas/contexto/client.get, Guest, acceso cruzado, rechazo de edición, configuración incoherente, perfiles deshabilitados y rol idempotente. Sin mocks. |
| Suite sin framework | PASÓ · 40 pruebas | Simulador y contratos. No valida stock ni pagos ERPNext. |
| Ruff y formato | PASÓ | Código propio. |
| Build de assets | PASÓ | Frappe, ERPNext, X POS web y app; no se descargaron binarios Electron/Cypress ni se probaron esas aplicaciones. |
| Servicio web local | PASÓ | Gunicorn bajo systemd de usuario, 127.0.0.1:8000, sin debugger. Respuesta ping y login HTTP real de Administrator. |
| Cliente Windows | PASÓ · conectividad | Chrome nativo Windows/Playwright alcanzó el servidor WSL y recibió pong. No constituye checkout E2E ni nueva prueba física de impresora. |

Las primeras ejecuciones revelaron detalles del runner: `set-config --parse` interpreta literales Python (True); el flag obsoleto `--skip-test-records` no debe usarse; instalar extras sin `-e` sustituye la fuente editable y rompe el build frontend. Corregidos comandos y documentación. La suite usa el instalador estándar de datos maestros ERPNext para crear Warehouse Type Transit y otras dependencias de una instalación previa al wizard; no se omitieron validaciones nativas para forzar fixtures.

**Hallazgo upstream confirmado U04 parcial:** el probe `open_multi_pos.integration.audit_xpos.receipt_context_probe` devolvió `native_profile_access_denied=true` y `xpos_receipt_access_denied=false`. El cajero A no puede leer documentalmente el perfil B, pero la función X POS de contexto devuelve su contexto sin ejecutar ese control. Solo se usaron entidades ficticias; no se registró el payload retornado. La prueba reproduce una llamada Python directa a la función whitelisted; no se presenta como ensayo HTTP de todas sus rutas.

Al cerrar aquel incremento, issue #3 seguía abierto: faltaba restringir esa ruta y probar directamente mark_invoice_printed, creación de facturas y reintentos. La siguiente sección registra el avance posterior. Los nueve casos aprobados prueban el perímetro OpenMultiPOS evaluado, no el aislamiento completo de X POS.

## P0 · Recibos, facturas e impresión por HTTP · 19/10/2026

Se añadieron adaptadores con `override_whitelisted_methods`, sin modificar core/upstream. El contexto valida marca concedida/habilitada, perfil vigente, asignación, permisos nativos y formato configurado; no vuelve al resolver cached original. El detalle valida cada documento y aplica permisos de campo antes de devolver valores. El registro de impresión admite solo POST, comprueba lectura/impresión nativa y derechos del perfil específico, y usa bloqueo de fila. Un rol de reimpresión en otro perfil no concede ese derecho al documento actual.

La inspección de creación/reintentos encontró autorización posterior a búsqueda de duplicado y escrituras con ignore_permissions. Se bloquearon 14 operaciones whitelisted del módulo de facturas, también para managers, incluyendo creación, borradores, fiscalización, listados y devoluciones/repetición. Solicitudes directas v1/v2 devuelven 403 sin mutar facturas, Stock Ledger Entry ni GL Entry. Esto no valida checkout nativo; conserva la puerta cerrada hasta issue #4. El inventario AST clasifica las 16 funciones whitelisted del módulo fijado y falla si cambia sin revisión.

Los ensayos adicionales encontraron una factura de otra marca de la misma empresa accesible por permisos documentales nativos. Se añadieron restricciones de lista/documento para OMP Cashier en Sales Invoice/POS Invoice, sin conceder escritura. Una prueba HTTP de `/printview` devolvió una página de esa factura pese al rechazo REST; se añadió un hook posterior a autenticación que valida documento e impresión antes del render. Ambas formas de URL de página, REST v1/v2, lista y API de HTML se cubren mediante solicitudes reales. No se afirma haber identificado o corregido toda la superficie de impresión upstream.

MariaDB produjo CHECKREAD bajo solicitudes concurrentes con bloqueo, traducido por Frappe a QueryDeadlockError. Se responde 409 y se deja el rollback al framework; no se resetea la transacción del llamador. Las pruebas reintentan únicamente registros abortados y verifican contador exacto y segunda impresión denegada al cajero sin permiso. No existe reintento automático de papel ni confirmación física en ese contador.

| Evidencia de este incremento | Resultado | Alcance y límites |
| --- | --- | --- |
| Suite HTTP con Gunicorn/MariaDB | PASÓ · 19 pruebas | v1/v2, URLs propias, ambas clases de factura, Guest, dos empresas, otra marca en la misma empresa, revocación, perfil/marca deshabilitados, formato arbitrario, campos restringidos, rutas bloqueadas y concurrencia. Sin mocks de autorización. |
| Suite Bench/MariaDB anterior | PASÓ · 9 pruebas | Regresión del perímetro marca/perfil sobre el sitio instalado. |
| Suite sin framework | PASÓ · 40 pruebas | Simulador y contratos existentes, no checkout ERPNext. |
| Ruff, formato y build | PASÓ | Fuentes propias; wheel incluye módulos y fixtures. |

Los fixtures HTTP son exclusivamente ficticios: facturas en borrador de un ítem sin stock y aperturas POS de saldo cero canceladas después de preparar los documentos. Tokens aleatorios permanecen en memoria; la suite restaura credenciales/roles y elimina secretos temporales. No se publican cuerpos de recibos, credenciales ni logs privados. El probe resuelve ahora el override y devuelve `native_profile_access_denied=true`, `xpos_adapter_access_denied=true`; es diagnóstico Python adicional, separado de la evidencia HTTP.

La revisión del resolver de Frappe identificó variantes `.html` de ambas páginas. El guard normaliza esas rutas igual que Frappe y las solicitudes HTTP negativas incluyen las cuatro formas; no basta comparar únicamente `/printview` literal.

El primer CI nuevo pasó 18 casos HTTP y falló con 500 en la página HTML de denegación. El preparador usa `--skip-assets`; la página de error de Frappe también carga bundles y necesita el build omitido en ese sitio fresco. Se añadió compilación de assets nativos antes de Gunicorn y se comprueban tanto JSON como HTML con 403, sin relajar la expectativa de autorización.

La matriz completa del incremento y sus límites están en [xpos-api-security.md](xpos-api-security.md). Las funciones Python originales upstream siguen intactas: llamadas internas por import requieren su propia revisión. Otras APIs de catálogo/clientes/reportes/cierres/exportación/archivos no quedan certificadas. Checkout, stock, pagos mixtos, caja, idempotencia de ventas, offline y recuperación continúan pendientes. DIAN desactivada; ningún nuevo ensayo físico ni uso de datos reales.

## P0 · Backend de caja nativa · 19/10/2026

Nuevo servicio `open_multi_pos.checkout`: terminal individual autorizada, cotización con ERPNext, apertura/cobro/cierre y consulta de estado. Se eligió Sales Invoice con is_created_using_pos y stock/contabilidad inmediatos. No se llama al create_invoice upstream ni a fiscalización interactiva. FBR activado y otras configuraciones no soportadas se rechazan antes de enviar. Las 14 rutas originales siguen cerradas; el frontend X POS no está conectado a este API.

Tres DocTypes propios: OMP POS Terminal (UUID, usuario/marca inmutables, deshabilitada por defecto), OMP Checkout Quote (huella financiera y vencimiento) y OMP Checkout Request (PK por terminal/UUID, hash de payload y quote UNIQUE). El claim, envío nativo y snapshot comparten transacción. Los journals privados usan inserciones internas después de autorizar; las facturas nunca usan ignore_permissions. Los permisos nativos de rol/empresa siguen activos dentro de una capacidad ContextVar limitada a documentos concretos. El cajero no recibe roles contables ni permiso de escritura directa por HTTP.

Se comprobaron precio/impuestos nativos, pagos COP mixtos y cambio del efectivo; los registros Bank no se presentan como confirmación bancaria. Artículos/bins bloqueados en orden estable, rechazo de stock insuficiente incluso con política global permisiva y serialización de cierre/cobro por perfil. Se fija la unidad de inventario: no se interpreta una unidad de venta de diez unidades como una unidad disponible. La marca persistida en el journal restringe facturas históricas aunque se reutilice su perfil.

El cierre ERPNext contiene un commit interno antes de asociar algunas facturas. Se mantiene ese comportamiento sin fork y se documenta su límite: retry idéntico recupera el cierre y repara asociaciones, sin volver a enviar facturas ni descontar stock. No se anuncia atomicidad completa del cierre ni recuperación de todos los fallos. Solo checkout propio carece de commits/rollbacks internos; 409 y respuesta incierta requieren consultar estado y repetir la misma clave.

| Evidencia local | Resultado | Alcance |
| --- | --- | --- |
| Migración | PASÓ | Tres DocTypes nuevos, índices UNIQUE/consulta y permisos mínimos sin roles contables. |
| HTTP nativo | PASÓ · 16 pruebas | Factura enviada, Stock Ledger y GL balanceado, impuesto ficticio calculado por ERPNext, mixtos/cambio, apertura/cierre, retry/payload/quote, concurrencia/última unidad entre perfiles, cierre concurrente, expiración/precio cambiado, revocación/acceso cruzado, perfil reutilizado, unidad de inventario, rechazo fiscal y snapshot. |
| Rollback contable real | PASÓ | Cuentas congeladas causan fallo nativo de GL; sin factura, SLE, GL ni claim adicionales. Misma clave funciona al corregir la configuración. |
| Contratos sin Frappe | PASÓ · 47 pruebas | Incluye siete contratos nuevos de Decimal, UUID, campos admitidos, cantidades y normalización; separado de la integración real. |

Fixtures únicamente ficticios; Stock Entry de preparación, facturas enviadas y cierres se conservan. Se restauran tokens/roles, precios, configuración y permiso temporal adicional; se deshabilitan perfiles/marcas/terminales de la suite. Ningún voucher ni log se publica. La migración encontró 550 trabajos pendientes sin consumidor: se instaló worker systemd de usuario para procesarlos sin purgar cola ni aumentar su límite; CI también arranca un worker.

Contrato, configuración y límites en [native-checkout.md](native-checkout.md). Falta pantalla autenticada y búsqueda/lector conectados al API, presentación/impresión nativa del snapshot, devoluciones, pruebas operativas de backup/restauración y revisión del resto de upstream. No se cambió core, no se hicieron pruebas físicas nuevas, no se transmitió a DIAN y no se habilitó operación con datos reales.

La repetición de la prueba concurrente reveló un cierre que omitía una venta recién completada: el bloqueo del perfil no refresca una vista REPEATABLE READ previa. Se añadió un Custom Field estándar de revisión en POS Opening Entry, incrementado con la venta; comparar snapshot/lectura bloqueada obliga a 409 si la vista está obsoleta, sin resetear transacciones. Se repitió la carrera y se añadió guard de eventos contra escrituras directas incluso con DocShare. El harness también descarta su snapshot diagnóstico antes de inspeccionar una cotización creada por HTTP; no modifica la transacción del servicio.

Regresión final local: 9 pruebas Bench, 19 HTTP de seguridad y 16 HTTP de caja aprobadas; carrera cierre/venta repetida seis veces adicionales sin fallos. Ruff/formato/Prettier, 47 contratos/simulador y build aprobados. Worker activo: short/default/long con cero tareas pendientes y cero fallidas tras procesar el backlog.

## P0 · Pantalla autenticada y recuperación · 19/10/2026

Nueva página `/omp_pos`, sesión cookie y CSRF Frappe, selección de terminales propias y contexto autorizado, cliente de mostrador del perfil, búsqueda por nombre/código/barcode, modo HID US opcional, carrito de unidades enteras, cotización del servidor, pagos mixtos, apertura y conteo/cierre. El catálogo comprueba permisos documentales, campos y grupos antes de responder; candidatos rechazados no dejan mensajes con sus datos en una respuesta vacía. No usa precios ni ledger del simulador.

Antes de enviar checkout, guarda solo terminal/UUID/quote/pagos por sitio/usuario en localStorage. Web Locks serializa pestañas del mismo origen/perfil; recarga consulta el estado y conserva exactamente la clave/payload. No coordina otros equipos/perfiles ni implementa offline. Un intento incierto bloquea nuevas ventas hasta recuperar un resultado o resolverlo en servidor.

Nuevo campo `OMP Checkout Request.abandoned` y POST `abandon_checkout`: mismo mutex/claim que venta, devuelve la factura si terminó o persiste un tombstone UNIQUE sin documentos financieros. Una solicitud tardía ya no puede vender esa clave/quote. No devuelve dinero externo y los conflictos conservan el intento. Se prueban resolución concurrente, repetición y cobro tardío rechazado.

Recibo escapado del snapshot histórico, impuestos y medios nativos, fecha local, pie/QR, perfiles 48/58/80 mm y script compartido de altura finita. Cargar/imprimir revalida lectura e impresión; no crea factura ni marca salida de papel. El botón solo pide diálogo y no incrementa automáticamente print_count. El simulador conserva su rotulado DEMO y usa los helpers compartidos de escaneo/layout.

| Evidencia local | Resultado | Alcance y límites |
| --- | --- | --- |
| Migración del journal | PASÓ | Tombstone persistente; índices únicos previos conservados, sin cambio de core. |
| HTTP nativo | PASÓ · 20 pruebas | 16 previas y fachada/catálogo, recibo/permisos/layout, resolución y carrera. Catálogo rechazado sin mensajes filtrados, perfil deshabilitado omitido. |
| E2E Chrome Windows → Bench/MariaDB | PASÓ · 1 recorrido | Login cookie/CSRF negativo, dos usuarios, cuatro facturas y cuatro SLE/GL, código HID simulado, mixtos/cambio, respuesta perdida antes/después del commit, retry con mismo UUID, recarga, dos pestañas con un solo POST, tombstone y cierre. Sin mocks del backend. |
| Recibo nativo | PASÓ · 3 PDF de una página | 48/58/80 mm, altura menor a 180 mm y ancho comprobado con pypdf. Error HTTP de recibo conserva venta y no reenvía checkout. Diálogo sustituido en navegador de pruebas; ninguna salida física nueva. |
| Teclado/responsive/axe | PASÓ | Enter de lector, Tab al botón de guardar y Enter; 390/768/1366 px sin desborde; sin violaciones axe en reglas seleccionadas. No acredita WCAG completa ni lector físico. |
| Regresiones | PASÓ | 9 Bench, 19 HTTP seguridad, 48 Python, Ruff/formato/Prettier, sdist/wheel; demo navegador y seis PDF previos conservados. |

El harness restaura hashes de contraseña, sesiones nuevas, roles, barcodes y configuración, y deshabilita terminales de suites. Credenciales efímeras pasan por stdin, sin argumentos ni archivos públicos. Capturas/PDF exclusivamente ficticios quedan fuera de Git. Un preparador separado deja una caja de revisión ficticia con credenciales locales modo 600; no sustituye una instalación productiva ni incorpora datos reales.

CI incorpora el E2E Chromium Linux después de las suites HTTP en un sitio nuevo y sirve assets propios con el middleware de desarrollo de Frappe. La validación de CI y commit se registra en PR #1. Próximo P0: lector y recibo nativo en hardware/controlador Windows, luego recuperación operativa y auditoría restante. Devoluciones, historial navegable de caja, otros clientes, offline, backups/restauración y aceptación productiva siguen pendientes. DIAN desactivada; sin transmisiones fiscales ni pruebas físicas nuevas.

Configuración de fecha: se detectó que el sitio local conservaba la zona por defecto de Frappe (Asia/Kolkata). Se configuró America/Bogota y un almacén, cliente y lista de precios separados para la caja ficticia de revisión, sin reescribir vouchers anteriores. Un recorrido adicional Chrome Windows validó apertura, venta, snapshot y cierre con esa configuración; CI fija Bogotá antes de crear los fixtures del sitio nuevo.


## Espacio administrativo y personalización · 20/10/2026

La rama `codex/business-workspace` se creó desde `origin/main` e incorporó la base de desarrollo validada. El alcance cambió a dos negocios, administración diaria, español latinoamericano, COP y el equipo Windows existente. La relación con entidades legales se elige durante el alta. No se exige otro modelo ni otra prueba física. Las fotos del propietario permanecen privadas; confirmó que los recibos se imprimen normalmente.

Añadidos `/omp`, menú con iconos y buscador, perfiles/contactos de negocio, primera cuenta humana desde instalación, equipo, inventario/productos/entradas, herramientas nativas de compras/finanzas/clientes y un recibo interno conjunto. Cesta de hasta dos negocios, misma moneda, una factura por negocio y transacción común. Se conservan las 14 rutas originales de factura X POS bloqueadas y la caja `/omp_pos`.

SKU automático: iniciales/prefijo editable, nombre normalizado y serie nativa. Clave de creación única en Item y hash de payload; reintento y recarga recuperan el mismo código. No se modifican códigos existentes. Entrada de stock con clave única y marca de abandono para solicitudes tardías. Ningún documento nativo se crea con `ignore_permissions`.

Dos extensiones de clase nativas permiten aperturas personales por negocio para administradores y validan la apertura de cada factura por usuario/perfil/empresa/fecha. Conservan las demás validaciones nativas. El cierre nativo consulta por propietario y perfil; una prueba usa dos administradores simultáneos y verifica que cerrar uno conserva abierto el otro.

| Evidencia local | Resultado | Alcance |
| --- | --- | --- |
| Python sin Frappe | PASÓ · 52 pruebas | Contratos, simulador, recibos, SKU y guard de publicación. |
| Ruff y formato | PASÓ | Fuentes propias Python y Prettier en assets/HTML/runner. |
| Bench/MariaDB | PASÓ · 9 pruebas | Regresión de permisos con marcas/empresas/cajeros. |
| Seguridad HTTP X POS | PASÓ · 19 pruebas | API v1/v2 y rutas nativas alternativas; sin ampliar accesos de cajero. |
| Checkout HTTP nativo | PASÓ · 20 pruebas | Stock/GL, impuestos, concurrencia, cierres, snapshots y rollback. |
| Espacio administrativo HTTP | PASÓ · 15 pruebas | Alta con entidad nueva/compartida; stock y SKU idempotentes/concurrentes; propiedad de producto; cesta de dos empresas; rollback del segundo hijo; abandono; snapshot/contactos; moneda USD y rechazo de cesta de monedas distintas; revocación/cancelación; dos administradores. |
| Caja anterior, Chrome Windows | PASÓ | Cookie/CSRF, cuatro facturas, stock/GL, dos cajeros, dos pestañas, respuesta perdida, abandono, recibo y cierre. |
| Espacio administrativo, Chrome Windows | PASÓ | Todas las herramientas nativas de compras/finanzas/clientes; SKU y entrada con respuesta perdida/recarga; cesta mixta y recibo; cambio español/inglés/formato; tutoriales/teclado; móvil 390 px; axe sin violaciones graves/críticas en la vista revisada. |
| PDF del recibo conjunto | PASÓ | Una página de 48 mm, altura menor de 130 mm para el caso ficticio de dos artículos; no equivale a prueba física. |
| Manual visual | REVISADO | Diez secciones y captura adicional del formulario SKU. Solo datos inventados; manifest SHA256 exacto. |
| Construcción | PASÓ | sdist/wheel; comprobar assets y DocTypes del índice antes de publicar. |

Se encontró contaminación de fixtures históricos de inventario por fechas de otra zona horaria: los intentos de reducir existencias chocaban con movimientos futuros del artículo ficticio reutilizado. La suite nativa ahora crea artículos nuevos por ejecución y conserva el ledger anterior; no reescribe vouchers para hacer pasar pruebas. Las 20 pruebas se repitieron con éxito. Las aperturas ficticias huérfanas de ensayos fallidos se cerraron nativamente, sin tocar documentos de una operación real.

La primera pasada de axe detectó contraste 4,48:1 en Ctrl K; se oscureció el texto y la repetición pasó. Se corrigieron permisos nativos faltantes de maestros para cuentas humanas y el idioma de los formularios embebidos. Un hook soportado ajusta mensajes comunes de ERPNext a español latinoamericano, sin parchear core.

Límites: no se habilitan devoluciones guiadas, offline, transmisión fiscal ni un puente de impresión. El navegador/controlador conserva cola, márgenes, encabezados/pies y puede imponer longitud fija. La nueva plantilla se validó en HTML/PDF; no se pidió otro ensayo físico. El manual y tutoriales se mantienen en español; la cobertura de traducción de formularios avanzados depende también de ERPNext. Backup/restauración aislada y revisión de APIs upstream restantes siguen en el plan antes de datos reales. La CI del nuevo PR se verifica por commit; esta tabla registra ejecución local.
