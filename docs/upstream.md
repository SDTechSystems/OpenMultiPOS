# Fuentes upstream revisadas

Fecha: 18/10/2026. SHAs completos y versiones en [`upstream.lock.json`](../upstream.lock.json). Checkouts temporales para inspección; no se redistribuyen como parte de esta app.

| Proyecto | Commit | Licencia | Evidencia |
| --- | --- | --- | --- |
| Frappe | 4515014c87ece6cb20ee91d2cfb121c5cbd1ff4a | MIT | pyproject.toml Python >=3.14,<3.15; package.json Node >=24; hooks.py y permissions.py |
| ERPNext | 5af6561f5aa48104559692fb4fd82f2580e8d338 | GPL-3.0 | pyproject.toml requiere Frappe >=16.50,<17; POS Invoice y POS Profile |
| X POS | 6392895a955f91b8c7d55574dc01ac5f19459dc3 | MIT | pyproject.toml Frappe >=16.50,<17; README, API, frontend y tests |

En X POS, pyproject declara Python >=3.10 mientras README pide >=3.14. El límite efectivo lo impone Frappe; no tomar metadata X POS aislada como garantía. README advierte que Electron no está listo para producción.

Enlaces reproducibles:

- [Frappe pyproject](https://github.com/frappe/frappe/blob/4515014c87ece6cb20ee91d2cfb121c5cbd1ff4a/pyproject.toml), [licencia](https://github.com/frappe/frappe/blob/4515014c87ece6cb20ee91d2cfb121c5cbd1ff4a/LICENSE).
- [ERPNext POS Invoice](https://github.com/frappe/erpnext/blob/5af6561f5aa48104559692fb4fd82f2580e8d338/erpnext/accounts/doctype/pos_invoice/pos_invoice.py): validate, validación de perfil/empresa y pagos. El comportamiento de stock también depende del modo POS/ledger y cierre; probarlo en instalación.
- [X POS invoices](https://github.com/kodlyft/xpos/blob/6392895a955f91b8c7d55574dc01ac5f19459dc3/xpos/api/invoices.py): create_invoice, find_invoice_by_local_id, insert/save con ignore_permissions.
- [Impresión X POS](https://github.com/kodlyft/xpos/blob/6392895a955f91b8c7d55574dc01ac5f19459dc3/frontend/src/composables/usePrintInvoice.ts): printview, iframe/navegador y Electron.
- [API recibos X POS](https://github.com/kodlyft/xpos/blob/6392895a955f91b8c7d55574dc01ac5f19459dc3/xpos/api/print_formats.py): contexto y contador de impresiones.
- [Tests de reintento X POS](https://github.com/kodlyft/xpos/blob/6392895a955f91b8c7d55574dc01ac5f19459dc3/xpos/api/tests/test_invoice_retry.py), [offline](https://github.com/kodlyft/xpos/blob/6392895a955f91b8c7d55574dc01ac5f19459dc3/frontend/tests/offlineSale.spec.ts).

Issues abiertos X POS consultados vía GitHub: respuesta vacía al revisar. No equivale a ausencia de errores ni a auditoría de vulnerabilidades completa. Ningún fork ni parche upstream se ha creado. Antes de uso real, revisar API completa y probar las rutas de permisos señaladas en el informe.
