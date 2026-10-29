# Protección inicial de APIs X POS

Validado el 19/10/2026 contra los SHAs de `upstream.lock.json`. Implementación en `open_multi_pos/xpos_security.py`, inventario en `xpos_routes.py` y hooks de Frappe en `hooks.py`. No se modifica Frappe, ERPNext ni X POS.

## Rutas evaluadas

Frappe aplica `override_whitelisted_methods` tanto a `/api/method/` como a `/api/v2/method/`. También se prueban URLs directas de los adaptadores, que ejecutan los mismos controles.

| Método upstream | Comportamiento instalado |
| --- | --- |
| `xpos.api.print_formats.get_receipt_context` | GET/POST autenticado. Marca habilitada y concedida, permisos nativos de empresa/almacén/perfil, asignación de usuario vigente, formato configurado y datos actuales autorizados. Rechaza formatos arbitrarios. |
| `xpos.api.print_formats.mark_invoice_printed` | Solo POST. Sales Invoice/POS Invoice autorizado, permisos nativos de lectura/impresión, empresa/almacén coherentes, documento no anulado y derechos de borrador/reimpresión del perfil concreto. Bloqueo de fila y actualización del contador sin alterar `modified`. |
| `xpos.api.invoices.get_invoice_details` | GET/POST autenticado con autorización de documento y marca. Respuesta limitada al contrato upstream, con valores sometidos a permisos nativos de campo. |
| `create_invoice`, `save_draft_invoice`, `discard_draft_invoice`, `delete_draft_invoice`, `finalize_fiscal_invoice` | 403 para todos, incluidos managers. No habilitar sin adaptar estos endpoints al contrato cotizado del servicio propio y ampliar sus pruebas. |
| `get_draft_invoices`, `get_unsettled_invoices`, `get_past_orders`, `get_invoices`, `search_invoices_for_return`, `get_invoice_for_return`, `get_last_invoice_rates`, `search_invoices_for_repeat`, `get_invoice_for_repeat` | 403 para todos. Lecturas y operaciones relacionadas pendientes de adaptadores con autorización de cada documento. |
| `xpos.api.invoices.fetch_exchange_rate` | Sin override; consulta global de monedas, sin acceso a facturas privadas. |

La suite clasifica mediante AST todas las funciones whitelisted del módulo `xpos.api.invoices` fijado: 14 bloqueadas, un detalle protegido y una consulta global sin modificación. No se presenta como inventario completo de APIs X POS.

## Acceso documental alternativo

Para OMP Cashier, hooks de lista/documento limitan Sales Invoice y POS Invoice a documentos POS de una marca habilitada y concedida. Comprueban enlaces de empresa/almacén y applicable_for_users. Son restricciones adicionales a los permisos nativos; no conceden roles contables. Escritura documental de cajeros permanece denegada en este incremento.

Un hook posterior a la autenticación protege las páginas `/printview` y `/<DocType>/<name>`, incluidas sus variantes `.html`, antes del render. Normaliza la ruta igual que el resolver de Frappe. Se añadió porque el ensayo HTTP devolvió una página de factura de otra marca aunque la API documental la rechazaba. Se prueban además REST v1/v2, `frappe.client.get_list` y la API nativa de HTML de impresión. Managers y otros roles mantienen sus permisos documentales nativos; los adaptadores X POS siempre exigen contexto autorizado.

## Concurrencia y alcance del contador

MariaDB puede abortar una lectura con bloqueo concurrente mediante CHECKREAD, que Frappe traduce a QueryDeadlockError. El adaptador devuelve **409** y deja que Frappe revierta la transacción completa. No ejecuta commits, rollbacks ni reintentos internos. Las pruebas reintentan solo el registro confirmado como abortado y comprueban que no se pierden incrementos ni se autoriza una segunda impresión a quien carece de reimpresión.

Un contador registra una declaración del cliente; no confirma salida de papel ni impide copiar/imprimir información ya leída. Ante 409 o pérdida de respuesta, consultar estado antes de decidir cómo registrar el resultado. No reenviar automáticamente el recibo a la impresora. La impresión productiva necesita un trabajo persistente y confirmación operativa independiente del cobro.

## Reproducción y límites

Ver comandos en [development.md](development.md): nueve pruebas Bench/MariaDB y 21 métodos HTTP reales en `scripts/test-xpos-http.py`, con dos workers/dos threads y datos ficticios. Se cubren dos empresas/cajeros, otra marca de la misma empresa, Guest, revocación, perfiles/marcas deshabilitados, formato arbitrario, GET de escritura, permisos nativos/campos, ambas clases de factura y concurrencia.

Los overrides protegen dispatch HTTP, no sustituyen llamadas Python internas a las funciones originales. Otras aplicaciones instaladas siguen siendo código confiable que requiere revisión. No se han auditado todas las rutas de reportes, catálogo, clientes, cierres, exportaciones o archivos de upstream; tampoco se certifica aislamiento total. Sitio de desarrollo con datos ficticios, DIAN desactivada y ninguna nueva prueba física. Al terminar ese incremento, checkout/stock/pagos/cierres nativos, idempotencia de ventas y offline seguían pendientes; el avance posterior se registra debajo.

Avance posterior: [caja nativa propia](native-checkout.md) validada con 20 pruebas HTTP, stock/GL, mixtos/cambio, idempotencia y cierre nativo. Las 14 operaciones originales siguen bloqueadas: ese frontend todavía no usa el contrato nuevo. Los hooks permiten escritura nativa solo durante la capacidad privada del servicio y vinculan las facturas nuevas a la marca registrada en su journal. La pantalla propia `/omp_pos` tiene E2E nativo cookie/CSRF; otras APIs upstream y offline siguen pendientes.

## Superficie nativa de cajeros: catálogo, clientes, stock, ventas y reportes

Avanza el pendiente de #3 sobre lo que un cajero (`OMP Cashier` + `Sales User`) alcanza por Frappe nativo. Dos marcas pueden compartir empresa, así que los permisos de usuario por empresa no las separan. `permissions.py` añade restricciones (solo restringen; los permisos nativos siguen aplicando) y `hooks.py` las registra. Managers y usuarios sin `OMP Cashier` no cambian.

| Recurso | Regla para cajeros |
| --- | --- |
| Item | Solo artículos sin `omp_business_brand` o de una marca habilitada y concedida. Cubre listas, REST v1/v2 y descargas de adjuntos privados, que delegan en el permiso del documento. |
| Customer | Solo el cliente de mostrador de un POS Profile accesible; únicamente lectura/impresión (no escritura ni alta). |
| Bin | Solo almacenes de una marca habilitada y concedida. |
| Sales Order, Quotation, Delivery Note | Denegados: la aplicación no los usa. |
| `frappe.desk.query_report.run`, `background_enqueue_run`, `export_query` y `frappe.desk.reportview.export_query` | 403 en `upstream_gate.authorize_request` (v1, v2 y `cmd`). Las consultas de reportes son SQL directo y no pasan por los hooks por registro; la caja solo usa `/omp_pos`. |
| `frappe.desk.doctype.dashboard_chart.dashboard_chart.get` | 403 para cajeros antes de resolver la caché o ejecutar el gráfico. El contrato acepta descriptores del cliente y la caché usa el nombre del gráfico, sin identidad de usuario. |

La prueba `test_native_dashboard_chart_routes_are_denied_to_cashiers` exige 403 para ambos cajeros por GET/POST, API v1/v2 y `cmd`, con lectura de caché y `no_cache`. Usa una caché ficticia temporal y conserva un control de lectura de manager. La suite HTTP ampliada aprobó sus 22 pruebas en el Bench desechable, incluidas esas 24 negativas y el control del manager. No se presentan como prueba de todos los gráficos ni del resto de metadatos.

Item Price no tiene lectura nativa para Sales User en el ERPNext fijado, por lo que no se añade hook. Límites pendientes: metadatos de listas de File, Address/Contact, nombres de Price List y otros reportes no inventariados. Se bloquean los ejecutores genéricos de reportes para cajeros, pero no se auditó cada reporte ni cada doctype nativo. No se certifica aislamiento completo. Prueba `test_native_catalog_customers_reports_and_sales_documents_respect_brand_scope`: Bench desechable local con los SHAs fijados (MariaDB 11.8.6, Redis 8.0.5, Python 3.14): 9 pruebas Bench, 21 HTTP de seguridad X POS, 20 de caja nativa, 19 administrativas, 11 de devoluciones y 11 de importación, sin fallos. Sin los hooks y el bloqueo, solo la prueba nueva falla. No se ejecutaron los recorridos de navegador; CI del PR repite la instalación nueva.
