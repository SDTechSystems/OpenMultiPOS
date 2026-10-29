# Informe de auditoría inicial

Fecha: 18/10/2026. Alcance: inspección estática de tres checkouts version-16 fijados en upstream.lock.json, repositorio inicial y validación del incremento propio. No es una certificación de seguridad ni una auditoría completa de upstream.

## Antes de los cambios

OpenMultiPOS partía de commit cbe3ca8, con README y LICENSE GPLv3. Sin app, CI, tests, instrucciones AGENTS, issues o PRs. Sin trabajo local previo que conservar. Acceso de escritura confirmado para SDTechSystems.

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


La primera instalación nueva de CI pasó las nueve pruebas Bench, 19 HTTP de seguridad, 20 de checkout, 15 administrativas y el navegador de cajero. El recorrido administrativo detectó metadatos iniciales de ERPNext pendientes antes de abrir Compras. Se añadió una migración nativa después de preparar usuarios/empresas de prueba y una aserción explícita de readiness. No se omite el asistente con banderas manuales; la instalación real requiere la configuración nativa completa.

## Cierre P0 de recuperación y revisión de APIs · 20/10/2026

Alcance de #7 confirmado por el propietario: terminar P0 y seguir devoluciones/importaciones/garantías/costos en #19–#22. La vista previa futura en Impresión de ERPNext se registra en #18. No cambia el alcance del hardware.

Se implementó un CLI privado de copia, verificación y ensayo de restauración. La copia usa el generador nativo de Frappe con todos los datos y archivos, configuración/clave fuera de Git, manifest SHA256 y comparación antes/después. Detiene y recupera web/worker/scheduler que estuvieran activos; un bloqueo evita copias simultáneas. No restaura encima de sitios existentes. El clon usa otra base, mantenimiento, scheduler desactivado y correos silenciados; la importación conserva validación nativa de SQL y versión. La comparación cubre 18 tablas completas, archivos y descifrado de un secreto cuando existe. Las comprobaciones numéricas se realizan en MariaDB, sin dinero en float.

Ensayo real local: reinicio de web/worker **y MariaDB/Redis**, misma cookie/CSRF, recuperación del mismo producto/SKU, entrada de stock y cesta ya guardados, y envío repetido de un producto pendiente sin duplicación. Una copia posterior se restauró en otra base/sitio con dos archivos ficticios (público/privado) y un secreto cifrado. Tablas y archivos iguales; cero diferencias débito/crédito, Bin/ledger o facturas enviadas sin GL. El segundo intento de restaurar sobre el mismo clon fue rechazado; HTTP devolvió 503 para el clon en mantenimiento. Se eliminaron copias aisladas fallidas/obsoletas del desarrollo; quedó un clon verificado, sin modificar documentos del sitio origen.

Revisión de superficie: inventario AST de 227 declaraciones whitelisted en el SHA fijado de X POS, incluidos módulos históricos y controladores. Se cierran por namespace todas las rutas HTTP salvo los tres adaptadores autorizados anteriores; también futuros métodos, cmd legado, alias por DocType, métodos de documento y cliente/service worker anterior. Los Singles/ajustes que upstream agregaba a boot sin lectura nativa se retiran para usuarios no administradores. No se modifica core ni se afirma que todo ERPNext o todas las dependencias transitivas estén auditadas. [Política y límites](upstream-api-review.md).

Validación local del incremento: 58 pruebas Python, 20 HTTP de seguridad (incluye todas las declaraciones cerradas y las rutas alternativas), 20 HTTP de checkout, 15 HTTP administrativas; Chrome Windows recorrió herramientas nativas, formularios, recibo compacto, teclado, móvil y axe sin errores. El ensayo de reinicio y el de restauración son scripts independientes y reproducibles. CI incluye ambos después de las suites existentes en una instalación nueva; su resultado final debe verificarse en el último commit antes de integrar.

Se añaden temporizador diario local, lanzador Windows, estado de copia/ensayo en Ajustes y procedimiento completo de recuperación. Captura actualizada de Ajustes: datos y fechas inventados, inspección visual y hash en manifest. Archivos operativos, copias, manifests locales, claves y logs no se publican ni se adjuntan como artefactos CI. No se habilitan destino externo de respaldo, red pública/TLS, offline, DIAN ni herramientas P1. El respaldo local no cubre pérdida del disco; el destino privado separado sigue siendo una configuración del operador.

Ajuste de arranque Windows: Microsoft documenta que systemd no conserva por sí mismo viva una instancia WSL. El lanzador inicia y comprueba un único cliente de mantenimiento en segundo plano con bloqueo de archivo; una segunda apertura termina sin crear otro. Se verificó lanzamiento real desde PowerShell/WSL y la comprobación de bloqueo, sin cerrar la distribución activa ni ejecutar otro ensayo físico.

## Vista previa en Impresión de ERPNext · #18 · 20/10/2026

Se añade un botón mediante el hook soportado `doctype_js` de Configuración de impresión y otro en Ajustes administrativos. Ambos abren `/omp_receipt_preview`, protegido en servidor para administradores. La muestra usa opciones guardadas y líneas inventadas, identificadas como muestra. Las ventas se leen del journal original; no se reconstruyen con contactos actuales. Cada factura exige permisos nativos de lectura/impresión, estado enviado y coincidencia con su negocio, empresa, perfil, almacén, moneda e importe. Una cesta exige además todas sus facturas e igualdad con las instantáneas individuales.

Los endpoints son GET de lectura: no cobran, crean documentos ni registran impresiones. La impresión es explícita y vuelve a autorizar el recibo antes del diálogo del navegador. La lista se limita a 30 facturas del negocio y 30 cestas recientes; el número completo permite consultar una factura anterior. El formato compacto y el preset del equipo existente se reutilizan. No hay investigación ni nuevo ensayo físico de hardware.

Validación local: 58 pruebas Python; Ruff; 19 HTTP administrativas sobre ERPNext real (incluyen muestra sin escrituras, contactos históricos, cesta completa, negocio ajeno/deshabilitado, factura anulada, documento inexistente, método POST rechazado y acceso Guest/cajero denegado). Chrome Windows verifica ambos accesos, muestra y recibo conjunto, impresión explícita con función del navegador interceptada, teclado y móvil de 390 px. Axe no detecta infracciones serias/críticas en la página nueva; no constituye certificación WCAG. Manual, tutorial y captura generada exclusivamente con fixtures ficticios. La CI completa se comprueba en el commit publicado antes de entregar para revisión.

## Devoluciones guiadas por negocio · #19 · 20/10/2026

Se añade Devoluciones al menú administrativo. Consulta facturas de caja autorizadas, cantidades pendientes y precios originales; calcula con el mapper nativo de ERPNext y registra una Sales Invoice de devolución vinculada, con pagos negativos y stock en el almacén original. Admite devolución parcial/total y reparto efectivo/transferencia. Una cesta se devuelve por factura/negocio, con operaciones separadas. El programa no ejecuta pagos externos ni transmite documentos fiscales.

El servicio toma bloqueos de perfil, factura e intento. Las cantidades previas y el saldo reembolsable se consultan con lectura actual, sin confiar en una vista antigua al esperar otro reembolso. La huella del cálculo detecta cambios antes de enviar. Una clave usuario/UUID vincula el payload a su nota/comprobante; reintentos recuperan el resultado, y un abandono bloquea solicitudes tardías. Inserción/envío nativos, SLE, GL, pagos, journal y revisión de apertura comparten transacción. Un fallo de cuenta nativa revierte documento, stock, contabilidad y claim. No se usa `ignore_permissions` ni se modifica core.

Inicio excluye las notas crédito del conteo de ventas, muestra el importe neto del día y distingue ambos tipos de documento. El comprobante guarda los datos del negocio de la venta original y vincula factura/nota. Usa el mismo preset compacto del equipo Windows. La restauración concilia ahora 19 tablas, incluido `OMP Return Request`. Las capturas, motivos, productos y referencias públicas son inventados.

Límites explícitos: series/lotes, fracciones, descuentos globales, cargos fijos, notas previas sin vínculo de línea y diferencias de redondeo se revisan en el formulario nativo, accesible desde la sección. El servicio no fuerza una devolución que no pueda conciliar. DIAN sigue desactivada. El conteo real de cierre sigue siendo no negativo; si el esperado de un medio resulta negativo después de un reembolso, el operador conserva/revisa la diferencia.

Validación local del incremento: 59 pruebas Python, incluido el recibo escapado; 11 pruebas HTTP contra ERPNext real con precios/impuestos históricos, stock/GL/pagos, devoluciones parcial/total, replay/cambio de payload, concurrencia, cantidades excedidas, abandono, cesta, apertura/cierre, acceso Guest/cajero y negocio revocado, cuenta deshabilitada y rollback. Chrome Windows cubre menú, cálculo, pérdida de respuesta con recarga/recuperación, comprobante, teclado, 390 px y axe sin infracciones serias/críticas en la pantalla nueva. La suite comprueba además otro administrador y documentos anulados; la evidencia final se publica con el resultado de CI del commit. No se pide ni afirma un nuevo ensayo físico de impresora/lector.

## Importar inventario · #20 · 20/10/2026

Se incorpora un flujo CSV en español: plantilla, validación con errores por fila, revisión de diferencias y confirmación explícita. Cada archivo pertenece a un negocio y almacén; cantidades adicionales, no reemplazo de saldos. Incluye alta con SKU automático o manual, actualización de nombre/grupo/precio, agregado de códigos y recepción de stock sin precio de venta. Límite de 100 filas y 256 KiB; UTF-8, separadores habituales de Excel y decimales precisos.

El servidor reautoriza cada operación. Los bloqueos y el hash de revisiones detectan cambios después de preparar. La entrada nativa consolidada, catálogo, precios, SLE, GL y journal comparten transacción; los reintentos conservan UUID/resultado. Se exige otra confirmación para contenido previamente aplicado. Abandonar bloquea llamadas tardías, y anular el documento original no provoca su recreación. Los archivos normalizados y journals son privados; el navegador solo conserva referencias. La conciliación de restauración cubre ahora 21 tablas, incluidos códigos de barras e historial de importaciones.

Validación local: 64 pruebas Python, Ruff y formato; 11 pruebas HTTP contra ERPNext real cubren importación mixta, stock/GL, precios históricos de recibos, duplicados, permisos, concurrencia, cambios posteriores, abandono, repetición explícita, rollback completo tras fallo contable, documentos anulados y entrada sin precio. Chrome Windows verifica plantilla, errores, pérdida de respuestas tanto al preparar como al aplicar, recuperación tras recargar, SKU, teclado, 390 px y axe sin infracciones serias/críticas en la sección. Guía, manual y captura revisada solo con fixtures inventados. CI ejecuta además instalación nueva, regresiones nativas, reinicio y restauración; se revisará el resultado del commit publicado antes de entregar.

Límites: productos simples de stock en Nos; series, lotes, variantes, paquetes, fracciones y precios especiales requieren formularios nativos. La confirmación de contenido repetido no identifica entregas físicas con archivos distintos. No se amplía hardware, offline, DIAN, garantías ni costos de importación. Las versiones Windows portátil/instalable y su configuración inicial siguen en #37/#38.

## Incremento #22: distribución de costos de compra (21/10/2026)

Alcance: LCV nativo guiado, estimaciones en borrador, monedas/tasas explícitas y recuperación. Conciliación de recálculos y márgenes quedan pendientes. Inspección del LCV y de `init_landed_taxes_and_totals` en ERPNext `5af6561f5aa48104559692fb4fd82f2580e8d338`; no se modifica core. No se escriben directamente SLE/GL desde el servicio OMP.

Entorno local nuevo en espacio de usuario: Python 3.14.8, Bench 5.29.1, MariaDB 11.8.6, Redis 8.0.5 y aplicaciones de `upstream.lock.json`, sitio desechable loopback. La instalación inicial falló por usuarios anónimos locales de MariaDB; se corrigió en esa instancia nueva y se recreó exclusivamente el sitio recién iniciado. La Papelera solo se usó como referencia de herramientas, sin restaurar su base de datos. Credenciales privadas fuera de Git.

- Contratos/simulador: **68 pruebas sin Frappe**, aprobadas; no validan stock productivo.
- Integración: **9 pruebas HTTP reales** de LCV: recepción/factura con stock, borrador sin efecto y edición nativa, envío y reintento, concurrencia (200 o rollback 409 con recuperación), unicidad, separación de negocios en la misma empresa, permisos de cajero, moneda USD/tasa explícita, vista obsoleta, cancelación, rechazo nativo sin LCV parcial e impuestos previos incluidos en valoración.
- Navegador: **1 recorrido Chromium/Playwright** con cookie/CSRF, teclado, borrador/recarga/envío, UUID conservado y un solo LCV. Sin errores JS, sin desbordamiento a 390×844 y 1366×900; axe de la sección: cero hallazgos en reglas WCAG automatizadas. No certifica accesibilidad completa.
- Captura del manual: generada del recorrido ficticio, inspeccionada y aprobada por ruta/hash en el manifest. El navegador colaborativo falló dos veces con `Preview automation snapshot timed out after 15000ms`; se validó con el flujo Playwright del repositorio.
- Lint y formato Python/JS/HTML y guard de publicación revisados junto con el commit. La revisión de implementación se hizo en esta sesión; no se presenta como revisión independiente.

Límites: no se verificó finalización de recálculos sobre ventas posteriores, no se certificó un nuevo restore de LCV ni hardware; conserva el preset confirmado. No se ejecutó la suite completa upstream ni se certifica compatibilidad universal. DIAN continúa desactivada; no hubo transmisión fiscal. La clave impide duplicar un intento, no identifica dos intentos nuevos del mismo flete físico. El cliente conserva el contenido del intento en su almacenamiento local hasta resolverlo y requiere el mismo usuario/sitio.

## P0 · Superficie nativa de cajeros (#3) · 22/10/2026

Se restringen para `OMP Cashier` Item (marca sin dueño o concedida), Customer (solo cliente de mostrador del perfil accesible, solo lectura), Bin (almacén de marca concedida) y se deniegan Sales Order, Quotation y Delivery Note. Los ejecutores genéricos de reportes y exportaciones devuelven 403 a cajeros. Las descargas de adjuntos de Item/Customer siguen el permiso del documento. Detalle en [xpos-api-security.md](xpos-api-security.md).

Validación: 64 pruebas Python, Ruff y formato. Bench desechable local con los SHAs fijados (MariaDB 11.8.6, Redis 8.0.5, Python 3.14): 9 pruebas Bench, 21 HTTP de seguridad X POS, 20 de caja nativa, 19 administrativas, 11 de devoluciones y 11 de importación, sin fallos. Sin los hooks y el bloqueo, solo la prueba nueva falla. No se ejecutaron los recorridos de navegador; CI del PR repite la instalación nueva. Pendiente: metadatos de File, Address/Contact, Price List, otros reportes. No se certifica aislamiento completo.

## Recuperación de costos de compra · PR #42 · 21/10/2026

La revisión reprodujo un bloqueo: el navegador conservaba el intento antes del POST, pero una compra cancelada podía impedir tanto el envío como una nueva vista previa. Consultar devolvía `not_found` y no existía abandono seguro. El servicio incorpora una marca privada por usuario/UUID/negocio bajo los mismos bloqueos de perfil y negocio del envío. Abandonar recupera un comprobante existente o bloquea envíos tardíos; no borra ni cancela documentos. La interfaz solo libera el intento tras observar un resultado del servidor y recupera el abandono aunque se pierda su respuesta. El estado de un LCV cancelado deja de depender de que su compra siga enviada.

Validación local de la corrección: 68 pruebas de contratos/simulador sin Frappe y 12 pruebas HTTP contra ERPNext real en los SHAs fijados, aprobadas. Las HTTP incluyen compra cancelada, repetición del abandono, rechazo de Guest/cajero y negocio ajeno, solicitud tardía, carrera envío/abandono, recuperación de un comprobante existente y cancelación posterior de su compra. No hay mocks de permisos, stock ni GL en esa suite.

La ejecución conjunta detectó un conflicto entre fixtures de ejercicio fiscal: la suite anterior ya creaba un ejercicio global que solapaba el de LCV. La preparación de LCV usa ahora `get_fiscal_year` nativo por empresa, renueva su lectura después de crear empresas por HTTP y crea un ejercicio acotado a la empresa solo si falta. Se repitieron los 12 casos en un sitio recién instalado y después de crear el ejercicio global de la suite anterior: ambas ejecuciones aprobaron en aislamiento, sin cambiar validaciones ni fuentes upstream.

Los ensayos se ejecutaron con Bubblewrap, espacio de red aislado sin salida externa, entorno vacío con variables permitidas, fuentes y herramientas de solo lectura y escrituras limitadas a scratch. Los contratos tuvieron límite de 90 s, CPU 60 s y memoria de 1 GiB. La integración usó MariaDB/Redis propios del espacio aislado y datos ficticios; límite de 900 s, dos CPU, 4 GiB de memoria, 192 tareas y scratch tmpfs de 3 GiB. No se expusieron credenciales, sockets ni servicios del sitio operativo al proceso de prueba.

El recorrido Chromium se amplía para comprobar pérdida de respuesta antes del envío y después de confirmar abandono, recarga, UUID y nueva operación. La ejecución local quedó bloqueada antes de abrir el navegador por ausencia de `libnspr4.so`; no se presenta como navegador aprobado. CI conserva el recorrido con sus dependencias de navegador y repite la instalación, regresiones y restauración. El comparador incorpora las cinco tablas nativas de LCV y su marca de abandono. La [ejecución CI del commit `8f943e08f235c2b0bacf11158c1680f14c4da3bc`](https://github.com/SDTechSystems/OpenMultiPOS/actions/runs/39721182887) aprobó los cuatro jobs: privacidad, Python, navegador demo y Bench real. El recorrido Chromium nativo confirmó pérdida de respuesta de abandono, recarga, nueva operación, teclado, 390/1366 px y cero infracciones axe en la sección. El reinicio y la restauración aislada aprobaron la conciliación de 27 tablas, dos archivos y secreto cifrado; se rechazó sobrescribir un sitio existente. PR #42 integrado mediante `ed8dcdf682f51022749e1b4e4eb969964a99af1c`.

Revisión de seguridad enfocada en autorización, aislamiento e idempotencia; no es una auditoría integral. Conciliación de recálculos posteriores y márgenes de #22 siguen pendientes. No se amplía hardware, offline, DIAN ni distribución Windows.

## Garantías · #21 · 22/10/2026

Primera implementación del alcance confirmado: reclamaciones ligadas a venta/artículo, estado, fecha de recepción, cierre y notas sobre Warranty Claim nativo. Alta idempotente con journal privado, recuperación tras respuesta perdida y abandono persistente; vínculos históricos protegidos y edición con revisión nativa. Una venta cancelada conserva el seguimiento existente. Sin pagos, reembolsos ni stock; sin periodos/plazos automáticos ni órdenes de servicio pagadas.

Validación local inicial: 68 pruebas Python, nueve pruebas Bench de permisos y nueve HTTP contra ERPNext real aprobadas en aislamiento sin red externa. Las HTTP verifican replay, contenido distinto con misma clave, negocios separados/entidad compartida, abandono repetido y solicitud tardía, carrera alta/abandono, edición obsoleta y recuperación, fechas/textos inválidos, cambio de vínculo/eliminación por REST, venta cancelada y denegación de Guest/cajero/negocio revocado. No usan mocks de permisos, stock ni GL. El fixture fiscal existente se traslada al setup HTTP compartido para ejecutar suites sobre una instalación nueva sin depender del orden; incluye la empresa adicional en USD. Regresiones locales posteriores aprobadas: 19 HTTP administrativas, 12 de costos y las nueve de garantías. El ensayo local comprueba escrituras síncronas; el worker y la restauración completos se repiten en CI.

El recorrido de navegador cubre pérdida de respuesta de alta y abandono, recarga, cierre, teclado, escritorio/móvil y axe. Su ejecución local queda pendiente por ausencia de bibliotecas Chromium (`libnspr4`, `libnss3`, `libasound`); CI instala sus dependencias y ejecuta el recorrido nativo. La restauración se amplía a 29 tablas. Resultados remotos y captura del manual pendientes antes de integrar. La revisión enfocada no equivale a una auditoría de seguridad integral.

## Ayuda, recuperación de garantías y cliente Windows · 27/10/2026

Se corrige el helper compartido de formularios: asignar una cadena vacía a un selector sin valor explícito eliminaba la primera opción. El formulario de garantía quedaba inválido y el navegador impedía enviarlo. Se conserva ahora la selección nativa inicial. El recorrido exige un formulario válido antes de enviar y confirma recuperación del alta y del abandono tras perder sus respuestas, recarga y cierre de la reclamación.

El menú y las acciones principales incorporan explicaciones por foco y puntero, con Escape, descripción accesible, conservación de descripciones anteriores, permanencia al mover el puntero a la ayuda y posición ajustada al viewport. No se añade una dependencia frontend. El manual explica estos controles y el uso de un único servidor Windows para compartir datos. La captura de garantías procede exclusivamente de fixtures ficticios, se revisó visualmente y se añadió al manifest por hash.

Validación local en un sitio desechable con los SHAs fijados: 68 pruebas Python de contratos/simulador, nueve de permisos Bench y 103 HTTP reales aprobadas. Desglose HTTP: 21 de seguridad, 20 de caja, 19 administrativas, 11 de devoluciones, 11 de importaciones, 12 de costos y nueve de garantías. Tres recorridos Chromium reales aprobados: administración, costos y garantías; incluyen teclado, móvil/escritorio, pérdida de respuesta y axe. La prueba adicional de tooltips confirma foco, Escape, descripción previa, hover persistente y límites a 390 px. Ruff, formato y Prettier aprobados. Estos resultados no suman los contratos a la integración como si fueran equivalentes.

Los procesos de ensayo se ejecutan sin red externa, con entorno explícito, fuente/herramientas de solo lectura y escrituras en scratch tmpfs de 3 GiB. Límites: dos CPU, memoria de 4 GiB, 192 tareas y 900 s por lanzamiento. Chromium necesita su espacio de direcciones virtuales; la memoria física se limita con cgroup, sin RLIMIT_AS. El entorno inicial carecía de assets de error nativos y producía 500 en vez de los 403 esperados; se usaron los assets compilados de los mismos commits de Frappe/ERPNext. No se cambió la autorización para hacer pasar las pruebas. El recorrido administrativo requirió repetir la apertura de la vista previa nativa; la versión final espera la carga del documento antes de comprobar su destino. Los ensayos no acceden al sitio operativo ni a sus secretos. No se repitieron en este incremento el worker completo, restauración ni hardware.

Se construyen ZIP portable e instalador del cliente Windows con Mono 6.14.1 y markdown2 2.5.5, ya presente en Frappe. El cliente abre el servidor en el navegador y guarda solo su dirección en el perfil de Windows. Las pruebas sin interfaz verifican HTTPS remoto, HTTP local y rechazo de esquemas ajenos, credenciales, parámetros y rutas inesperadas. El instalador incluye el cliente, manual y licencia como recursos; sus recursos se verifican antes de entregar. El manual HTML lleva las imágenes aprobadas incorporadas y puede consultarse sin conexión. El ZIP incluye código correspondiente e instrucciones de compilación. Se registran versión, requisitos, hashes y herramientas en build-info.json y SHA256SUMS.txt.

Los ejecutables están sin firma y no se afirma reproducción byte a byte. Compilar y ejecutar contratos bajo Mono no acredita instalación, accesos, registro, actualización, desinstalación ni WinForms en Windows. Hyper-V responde, pero esta sesión no tiene permiso de inspección de la VM; el propietario no puede revisarla ahora. La aceptación en Windows limpio sigue pendiente. Los paquetes son clientes y no incluyen ERPNext/Frappe, WSL ni una instalación autónoma del servidor. #37/#38 permanecen abiertos. El asistente completo, la conciliación restante de #22, la revisión restante de #3 y la activación del acceso remoto siguen pendientes; no se declara aptitud para producción. La guía de Tailscale propone la conexión privada, pero no configura cuentas, políticas, proxy ni HTTPS en la instalación operativa.

## Valoración posterior y margen bruto · #22 · 27/10/2026

La rama de entrega añade una consulta administrativa de recálculos y margen en Costos de compra. Conserva los permisos nativos de Gross Profit y de las tareas. Una tarea enviada abierta de valoración o contabilidad de la empresa, o una tarea contable sin empresa, oculta los importes. También los oculta una configuración de informe de instantánea. Con las colas despejadas, ejecuta Gross Profit nativo, sin informe preparado, con empresa y almacén derivados del contexto. El período está limitado a 366 días. Se informa alcance de subalmacenes, moneda contable, fecha y zona de consulta; no se promete actualización automática ni utilidad neta.

Validación local: 16 HTTP de costos aprobadas, incluidas las doce anteriores. El nuevo ensayo crea una recepción a costo 1.000, vende a 2.500 y envía un costo adicional de 500 sobre cinco unidades. Se observa una tarea nativa pendiente, se comprueba que un estado fallido oculta datos y se ejecutan los recálculos nativos. Con la separación contable activada, completar la tarea de stock crea tareas contables separadas y la vista continúa bloqueada hasta completarlas. El resultado nativo cambia costo de venta de 1.000 a 1.100 y margen de 1.500 a 1.400. Se comprueban SLE de -1.100, costo contable de 1.100 y GL balanceado. No se sustituyen los motores de stock, GL ni margen por mocks.

Otros casos comprueban rechazo de Guest/cajero y GET, fechas inválidas y período excesivo, ventas de otro almacén bajo la misma empresa, y exclusión de importes para un informe configurado como instantánea. La prueba de tarea contable parcial persiste un fixture de interrupción sin encolar un worker que compita con la lectura; se cancela por el controlador nativo y se restaura la configuración de documentos permitidos. Esta prueba valida la lectura de ese estado, no afirma reproducir una interrupción física del worker. Un error inicial de limpieza de ese fixture dejó una tarea abierta y la consulta bloqueó correctamente las ejecuciones posteriores. Se corrigió la limpieza y se canceló el fixture aislado antes de repetir; no se alteró el bloqueo del servicio.

Chromium real aprobado en 1366/390 px: consulta de margen, teclado, cambio de fechas que limpia resultados, envío que invalida la consulta anterior, ocultación de columnas de margen durante recálculos, recuperación de LCV y abandono, cero infracciones axe en la sección. Se conserva la consulta bajo demanda; no hay sondeo automático, caché de importes ni dependencia frontend nueva. Las 68 pruebas de contratos/simulador, Ruff, formato y Prettier también aprobaron. Los ensayos usan el entorno aislado y los límites de la sección anterior, sin sitio operativo ni datos reales. La comparación de restauración añade tres tablas nativas de recálculo, para 32; su ensayo completo se repite en CI antes de afirmar esa cobertura.

La validación remota del incremento anterior en `72b56fa749f8e984ce6485d2ab5caa2a364f519e` aprobó privacidad, Python, navegador demo, construcción de clientes y Bench real, incluido reinicio/worker/restauración de 29 tablas: [ejecución 40619160431](https://github.com/SDTechSystems/OpenMultiPOS/actions/runs/40619160431). Ese resultado precede a este cambio de valoración y no acredita todavía sus 32 tablas. No se modifican core, hardware, DIAN, operación sin conexión ni el sitio operativo.


La ejecución remota del cambio de valoración en `30925d0767f2d74b3ffb9da4839ab191c883844b` aprobó los cinco trabajos, incluido Bench con worker, reinicio y restauración de 32 tablas: [ejecución 40622846948](https://github.com/SDTechSystems/OpenMultiPOS/actions/runs/40622846948). Este resultado no acredita todavía la preparación reanudable posterior.


## Preparación reanudable

Nueve pruebas HTTP nativas aprobadas en sitio desechable: reintentos concurrentes con recuperación tras conflicto, un solo negocio, abandono que bloquea escrituras tardías, contraseñas excluidas del journal y nunca restablecidas por replay, cursor persistente, huellas vigentes, existencias reales, cuenta inicial única incluso tras desactivarla, rechazo de Guest/GET/cajero y permisos privados. El cierre satisfactorio usa registros de servicio sintéticos en un directorio exclusivo de prueba; no demuestra por sí mismo que exista un respaldo restaurable. El ensayo real de recuperación sigue siendo una validación separada.

Chromium real aprobó la reanudación tras recarga, foco de teclado, recuperación de una respuesta perdida del alta de cuenta, exclusión de contraseña de localStorage, cierre deshabilitado con requisitos pendientes, escritorio/móvil y cero infracciones axe en el asistente. Las 68 pruebas ordinarias, Ruff, formato, Prettier y tooltips aprobaron. Las nuevas tablas de progreso y solicitudes se incluyen en la comparación de restauración de 34 tablas. La ejecución remota de este incremento queda pendiente antes de acreditar esa ampliación.


La regresión completa de navegador del espacio administrativo aprobó compras/finanzas/clientes nativos, inventario, cobro mixto, devoluciones, importación, preferencias, manual, teclado, móvil y axe. La prueba de Print Settings ahora espera el selector de negocio poblado y el botón de vista previa habilitado, en lugar de depender del evento domcontentloaded de la ventana nueva. Mantiene la comprobación de la URL y verifica que la pantalla esté utilizable.

## Construcción limpia del servidor WSL

La validación completa de `374b0bd869a3f59dac5951f29e86f211cacf56cc` aprobó los cinco trabajos CI: [ejecución 40628651059](https://github.com/SDTechSystems/OpenMultiPOS/actions/runs/40628651059). El ensayo final informó restauración aprobada, 34 tablas, dos archivos de prueba, secreto cifrado conservado, rechazo de sobrescritura de sitio existente y aislamiento HTTP 503. Esto acredita la ampliación del respaldo de la preparación reanudable, no la distribución Windows del servidor.

Se creó una distribución WSL2 Ubuntu 26.04.1 x64 nueva y exclusiva para construir el servidor, sin copiar la instalación operativa. Antes de ejecutar dependencias del proyecto se desactivaron montajes Windows e interoperabilidad, y se ejecutó el código de aplicaciones como usuario UID 1000 sin sudo, con entorno explícito y sin credenciales del host. Se exportaron las fuentes públicas de 374b0bd y el constructor. No se exportó todavía una imagen distribuible.

`server/build-image.sh` reutiliza el preparador existente y sus tres SHA fijados. La construcción real completó dependencias y assets de Frappe, ERPNext, X POS y OpenMultiPOS con Python 3.14.4, Node 24.22.0, Bench 5.29.1 y Yarn 1.22.22. La descarga Node se verificó contra el SHA256 oficial. Se observaron avisos upstream de Browserslist y dependencias peer del frontend X POS, sin fallo de construcción. No se cambió core para eliminarlos.

La primera inspección detectó Nginx iniciado por los paquetes, aunque existía policy-rc.d. Se detuvo únicamente en la distribución nueva y se cambió el constructor para enmascarar MariaDB, Redis y Nginx antes de instalar paquetes. Se repitió el constructor corregido con resultado cero. La comprobación posterior confirmó los tres servicios enmascarados e inactivos, los tres SHA esperados y ausencia de montajes Windows.

El control `server/image_contract.py` aprobó la imagen de trabajo: cero sitios, cero esquemas comerciales y cero contraseñas Linux reutilizables. Tres nuevas pruebas verifican rechazo de un sitio, credenciales comunes/Redis, enlace de configuración, esquema comercial y contraseña Linux. Las 71 pruebas ordinarias, Ruff, formato, Prettier y sintaxis Bash aprobaron. Este control no sustituye la inspección completa de la imagen ni prueba el arranque de una aplicación: siguen pendientes inicialización privada, controles Windows, sellado/manifiesto/licencias, exportación y aceptación de instalación/actualización/recuperación/desinstalación. La distribución nueva permanece como entorno de construcción y sus servicios están detenidos.

## Inicialización privada del servidor y permanencia de WSL

Se exportó la base limpia únicamente a un archivo privado de QA y se importó en una distribución nueva de pruebas. La base original se conserva sin sitio. Se implementó `server/first_run.py`: intento privado con escritura atómica, contraseña por entrada oculta/stdin, cuenta MariaDB temporal retirada en finally, claves nuevas y llamadas al instalador/migrador nativo. La primera prueba detectó que la API nativa necesita la inicialización transitoria `new_site=True`, igual que el comando oficial `bench new-site`; se corrigió sin modificar flags de finalización del setup. El mismo intento pudo completar después la instalación. No se utiliza force ni borrado automático de sitio/base.

En la copia privada se crearon Frappe, ERPNext, X POS y OpenMultiPOS sin datos comerciales. Windows autenticó por HTTP loopback con la contraseña generada para QA. `/omp` respondió 301 a `/desk`, conservando la obligación de terminar el asistente nativo. Los ocho servicios comprobaron estado activo; MariaDB informó skip_networking ON y cero cuentas temporales de bootstrap. Se verificaron la conservación del registro/contraseña al repetir setup y el proxy realtime por socket Unix.

Se observó que systemd no mantiene activa la distribución WSL cuando termina la sesión ejecutada desde Windows. Se añadió una sesión `serve` que conserva stdin abierto, evita dos controladores simultáneos y realiza parada ordenada al recibir stop o EOF. La primera sesión de prueba terminó con cero; se apagó y arrancó de nuevo únicamente la distribución QA. Windows volvió a autenticar con la contraseña original y aprobó la conexión autenticada al namespace Socket.IO después de ese arranque en frío. MariaDB, Redis y el backend permanecen privados; el único listener de la aplicación es loopback 8089. No se configuró Tailscale ni otro acceso remoto.

Las 77 pruebas ordinarias, Ruff, formato y Prettier aprobaron. Las nuevas pruebas cubren replay completado sin cambios, rechazo de sitio ajeno, intención persistente sin falso éxito, permisos 600, contraseña fuera de argumentos/registro, retirada de cuenta temporal ante fallo nativo y configuración de sockets/cola persistente. Esto no acredita todavía recuperación de una interrupción a mitad de creación del esquema Frappe, ni prueba completa del asistente nativo en navegador, ni aceptación de instalación Windows limpia. Siguen pendientes esos ensayos, el controlador Windows, el sellado y la exportación final con manifiesto/licencias. Los logs y credenciales QA permanecen privados y fuera del repositorio.


## Recuperación de la creación inicial del esquema

El inicializador incorpora una recuperación conservadora: verifica la propiedad mediante el intento root y el site_config, consulta cuentas y tablas comerciales, y rechaza sitios completados, ajenos, con enlaces, archivos subidos o datos de operación. Guarda el intento anterior con sus credenciales privadas, mueve sus archivos fuera de sites y crea otra base con secretos nuevos. No ejecuta DROP DATABASE ni borra archivos. El registro y el movimiento se sincronizan a disco; una interrupción entre movimiento y actualización del registro permite repetir la operación. Se limita a tres intentos conservados antes de exigir revisión local.

En una distribución QA nueva se inició el instalador real y se terminó abruptamente WSL durante Updating DocTypes de Frappe. La recuperación posterior completó los cuatro módulos y la migración. La comprobación confirmó 19 tablas del esquema anterior todavía presentes, archivos archivados con las credenciales originales, base nueva distinta, cuenta temporal retirada y rechazo de otra recuperación al quedar instalado. El ensayo usa datos exclusivamente sintéticos y conserva ambas bases en la copia privada de QA. No se modificó la base limpia de construcción ni la instalación operativa.

Las 83 pruebas ordinarias, Ruff/formato y Prettier aprobaron. Las pruebas nuevas verifican consultas de solo lectura, repetición del archivado, rechazo de cuentas/documentos/archivos/enlaces ajenos y persistencia de la rotación si falla el intento siguiente. El ensayo abrupto prueba esta fase de creación; no certifica todos los posibles fallos de disco ni sustituye el respaldo/restauración de una instalación en uso. El controlador Windows, la aceptación del asistente nativo completo y los paquetes finales siguen pendientes.

Windows también autenticó en el sitio recuperado y comprobó que `/omp` sigue exigiendo el asistente nativo. La sesión QA de control se cierra al terminar las pruebas; la copia con credenciales se conserva únicamente como evidencia privada.

## Control Windows del servidor

Se añadió un controlador WinForms con importación condicionada al hash de la imagen, contraseña inicial confirmada, preparación/recuperación, ubicación visible, inicio, parada ordenada, aplicación y manual. Usa procesos WSL con argumentos validados, secretos por stdin UTF-8 y protocolo local 1 sin credenciales. Mantiene una sola ventana por instancia y espera el cierre; no fuerza la terminación ni elimina distribuciones o carpetas previas. Una importación interrumpida con carpeta existente queda conservada para revisión; su resolución guiada necesita validación con el paquete final.

La primera ejecución Windows detectó una sobrecarga de String.Split disponible en Mono pero ausente en .NET Framework. Se corrigió y se fijó compilación x64 con referencias de Framework 4.8. La siguiente prueba identificó que entrecomillar flags simples hace que WSL los interprete como comando Linux; se corrigió para entrecomillar únicamente valores que lo necesitan. Se cierra el stream base de stdin para evitar que otro escritor agregue una marca BOM. Estas incidencias no se detectaron solo con compilación Mono.

El ejecutable real aprobó en Windows el protocolo de estado, el transporte JSON de un texto ficticio con Unicode, salto, comillas y barra, el evento ready del servidor y la parada por EOF en OpenMultiPOS-RecoveryQA. Las pruebas propias aprueban comillas, nombres acotados y rechazo de imagen corrupta/manifiesto incompleto. Las 84 pruebas ordinarias, Ruff/formato y Prettier aprobaron. CI construye el controlador junto al cliente y ejecuta sus contratos también en un runner Windows.

La automatización visual de Windows no pudo inicializarse: node_repl rechazó sandboxCwd por el URI del workspace WSL. No se sustituyó por otra automatización de UI. Quedan pendientes revisión visual/teclado, importación de imagen sellada, instalación completa y aceptación en Windows limpio. El candidato carece de imagen de servidor y no se presenta como instalador final. Registros y datos QA siguen privados.


La CI del controlador en `270fb241b33e9ca901c8afee078e8980e3ca1576` aprobó privacidad, Python, navegador demo, construcción de clientes/controlador y contratos del ejecutable entregado sobre Windows: [ejecución 40642979402](https://github.com/SDTechSystems/OpenMultiPOS/actions/runs/40642979402). Bench se omitió en ese push; esta CI no sustituye la prueba QA local del proceso WSL ni acredita la interfaz visual del controlador.


## Imagen sellada y paquetes completos de aceptación · 28/10/2026

`server/seal_image.py` incorporó los manifiestos de versiones Ubuntu, fuentes Ubuntu, entornos Python, revisiones upstream y herramienta de primera ejecución. El sellado rechazó sitios, esquemas comerciales, estados privados de instalación, intentos retenidos, SSH y credenciales reutilizables. Detuvo journald y el escritor de entropía antes de retirar identificadores, registros, claves de host y cachés. La distribución se exportó en frío sin volver a iniciarla.

El archivo comprimido privado tiene 1.579.694.080 bytes y corresponde a `3f6e2da1a05c3ca8e26da36619fae17486386018`. Una inspección completa de sus 209.339 miembros verificó rutas, configuración, identidad y manifiestos: cero sitios, cero esquemas de aplicación y ninguna identidad reutilizable detectada. El control no sustituye una auditoría exhaustiva de cada dependencia. La distribución de construcción sigue detenida; las copias inicializadas nunca se vuelven a exportar como imagen limpia.

Una nueva copia importada desde ese archivo completó la creación nativa del sitio, las cuatro aplicaciones y la migración, sin copiar un helper corregido después de importar. En Windows, el controlador aprobó estado, transporte Unicode por stdin, inicio y parada. El mismo ejecutable importó la imagen real en otra distribución QA mediante `--verify-import` y comprobó que aún no había sitio inicializado.

`scripts/build-windows-server.py` reúne el controlador, la imagen y su manifiesto, el manual, fuentes públicas y hashes. `ServerInstaller.cs` copia el programa por usuario, crea acceso de Inicio y registro de desinstalación. Verifica la imagen antes de reemplazar archivos y conserva los reemplazados. La distribución WSL y sus datos quedan separados. El contrato Windows `--verify-installation` aprobó alta, actualización, rechazo de imagen alterada, acceso, HKCU, desinstalación y conservación de datos ficticios. Usó una imagen sintética pequeña: no acredita la interfaz ni una instalación completa en Windows limpio.

La primera configuración nativa se recorrió con Chrome Windows sobre la imagen recién instalada, cookie y CSRF reales. El formulario creó un usuario personal, una entidad ficticia colombiana y su plan PUC nativo. Respondió con estado ok; un inicio posterior con la cuenta personal abrió `/omp` y comprobó COP, Colombia y 2.503 cuentas nativas. No se marcaron banderas de configuración de forma artificial. El primer verificador rechazó erróneamente el fragmento legítimo `#home` de la URL después del éxito; la comprobación posterior comparó su ruta y validó los documentos persistidos. El recorrido usó English en el asistente ERPNext; no acredita todavía que la primera pantalla nativa proponga español automáticamente.

Las 88 pruebas ordinarias, Ruff, formato y Prettier aprobaron. Las comprobaciones existentes de la caja no se presentan como pruebas nuevas de esta imagen. Pendientes: aceptación visual/teclado de WinForms, Windows limpio sin herramientas de desarrollo, migración de backend con copia/restauración y cierre de fuentes y licencias antes de compartir. Se recopilaron 356 de las 374 versiones de fuentes Ubuntu del inventario; 18 requieren recuperación adicional. El inventario por sí solo no acredita el código fuente correspondiente completo. Los candidatos están sin firma, privados y no aprobados para producción.


## Restricción adicional de gráficos para cajeros · 28/10/2026

El gate de cajeros también rechaza `frappe.desk.doctype.dashboard_chart.dashboard_chart.get`, antes de resolver la caché compartida por nombre de gráfico o calcular su contenido. El endpoint nativo acepta descriptores del cliente y no es necesario para la caja propia. No se modifica el código upstream ni se impide el uso nativo de managers.

La suite real de seguridad HTTP aprobó 22 pruebas. El caso nuevo conserva una caché temporal ficticia, confirma que el manager puede leerla y exige 403 del gate para dos cajeros, GET/POST, v1/v2 y `cmd`, con caché y `no_cache`: 24 negativas. El resultado no acredita aislamiento integral; siguen pendientes metadatos File, Address/Contact, Price List y otras rutas de reportes.


## Contrato cerrado de HTTP para cajeros · 28/10/2026

`cashier_http.py` aplica una lista explícita de métodos y lecturas a OMP Cashier sin System Manager. Usa la precedencia real de `cmd` y el router Frappe fijado para distinguir v1/v2, listas, documentos, copias, metadatos y métodos. Rechaza funciones nuevas por defecto. Conserva las once llamadas de Caja, los tres adaptadores autorizados, sesión, lectura nativa acotada e impresión de facturas guardadas con permisos. Las listas no admiten expansiones ni campos/filtros de otras tablas y tienen un máximo de 100 filas. Los administradores y servicios Python internos conservan el comportamiento nativo.

File, Address, Contact y Price List no tienen acceso HTTP genérico para cajeros. Una descarga exige padre Item/factura actual y accesible más permiso nativo del archivo, aun con propietario o compartición. Se probaron URLs duplicadas, selección por fid y alias heredados. El ensayo inicial detectó que un padre inexistente dejaba su nombre en el registro de mensajes del error: se corrigió limpiando ese mensaje antes de denegar. La redirección de Inicio/Desk se implementó con una respuesta HTTP temporal, porque una excepción Redirect desde autenticación no recibe el tratamiento de las páginas web de Frappe.

El resultado final fue 25 pruebas HTTP de seguridad aprobadas, con comparación de listas filtradas entre RPC, REST v1 y REST v2. Las 20 pruebas de checkout nativo aprobaron stock, GL, pagos y concurrencia. El navegador Chromium real aprobó cookie/CSRF, respuestas perdidas, clave durable, abandono, pestañas concurrentes, cierre, segundo cajero y móvil. La revisión de código adicional fue automatizada por un agente, no una auditoría independiente externa. No se modifica core ni se afirma una auditoría integral del framework. La imagen sellada anterior debe reconstruirse con este contrato antes de entregar.

Se recuperaron las 18 versiones de fuentes Ubuntu faltantes desde publicaciones oficiales de Launchpad, con tamaño y SHA256 de los contenidos cotejados contra sus dsc. El conjunto cubre las 374 versiones inventariadas. No se validaron firmas OpenPGP de esas recuperaciones; el cierre de fuentes/licencias del resto de dependencias sigue en curso.


## Idioma de la primera configuración nativa · 28/10/2026

Una extensión `setup_wizard_requires` conserva el asistente nativo y propone el idioma configurado del sitio, usando sus nombres de idioma. Admite el código regional mediante su idioma base; respeta una selección previa y deja el valor nativo si el código no está disponible. No modifica core, validaciones ni estado de configuración.

Una copia QA sin sitio recibió los cuatro archivos públicos nuevos y completó la instalación nativa. Chrome Windows inició sesión y abrió su primer asistente: boot.lang es, campo de idioma Español. No se completó ni se marcó artificialmente el asistente. La prueba de lógica persistente cubre configuración es/es-CO, selección previa, código ausente/desconocido y reentrada, y se ejecuta en CI. El ensayo nativo completo de empresa/cuentas del incremento anterior sigue siendo evidencia separada.


## Respaldo y ensayo local guiados · 28/10/2026

El controlador Windows añade Crear copia y Comprobar recuperación, con ayuda y ejecución fuera del hilo de interfaz. Exige servidor detenido y reutiliza operations.backup/restore_drill. El helper root toma el bloqueo de vida, rechaza servicios activos y habilita únicamente base y Redis durante la operación. Retira la cuenta temporal de base y detiene servicios en finally. Un clon de ensayo conserva el aislamiento nativo y no sustituye el sitio original.

Una copia y un ensayo reales aprobaron sobre PackageQA ficticio mediante el nuevo helper. El controlador compiló y sus contratos aprobaron. Se añadió rechazo de servidor activo/no preparado/controlador concurrente y comprobación de limpieza ante fallo. No se repiten pruebas contables ni se reconstruye la imagen completa en este incremento. Los servicios dejan de habilitarse al arranque WSL para evitar actividad de fondo al consultar el estado. La aceptación visual Windows y la entrega final siguen pendientes.


## Fuentes verificadas para empaquetado · 28/10/2026

El nuevo constructor de fuentes coteja Source y Version de cada dsc con el inventario exacto de la imagen, verifica tamaños y SHA256 de sus contenidos y contrasta la cobertura Python con ambos entornos. Ese control encontró seis resultados apt cuya versión no coincidía con la solicitada; se recuperaron las versiones correctas desde Launchpad. El estado exitoso del descargador no se usa como prueba de correspondencia.

El empaquetador incluye solo los archivos verificados, sin registros, temporales ni rutas locales del recolector. Divide las fuentes en ZIP independientes sin recomprimir archivos ya comprimidos, para reducir CPU y permitir su distribución por partes. Conserva versiones y sumas en sources.json. Para barcodenumber se conserva el wheel publicado con fuente Python y GPL3, y se declara la ausencia upstream del COPYRIGHT referido; no se inventan avisos ni se afirma revisión legal externa.
