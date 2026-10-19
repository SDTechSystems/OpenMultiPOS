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

Se completará con comandos y resultados al cerrar la implementación. Prueba física de impresora y lector: REQUIERE HARDWARE. Instalación y venta real ERPNext: NO EJECUTADO por servicios ausentes.
