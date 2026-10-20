# Offline y sincronización

Estado: investigación de fuentes; NO validado para operación comercial.

X POS incluye `frontend/src/composables/useOfflineSale.ts`, `stores/offlineStore.ts`, persistencia vía dbBridge y motor Electron `frontend/electron/sync/syncEngine.ts`. Hay tests con mocks de cola/recibo y reintento en backend. No se han ejecutado sus suites ni pruebas de caída de red en este entorno.

`xpos/api/invoices.py::find_invoice_by_local_id` busca documento enviado por local_id y almacén antes de crear. Esta búsqueda por sí sola no demuestra unicidad bajo solicitudes simultáneas. La rama de retorno duplicado se alcanza antes de la validación posterior del perfil: requiere prueba negativa de permisos y aislamiento.

Contrato futuro: UUID de transacción + terminal + usuario + marca/entidad/almacén + fecha UTC + secuencia + hash de payload. Unicidad persistente y atómica; repetir idéntico devuelve el original, repetir clave con payload diferente se rechaza. Stock insuficiente genera conflicto visible sin borrar operación. Revalidar permisos y precios al sincronizar. Marca y recibo históricos conservan su contexto.

Pruebas pendientes: desconectar en cobro y después del commit/antes de respuesta, reconectar dos veces, dos terminales contra última unidad, permiso revocado, cambio de precio, clave repetida y otro almacén. No cachear credenciales para habilitar offline sin auditoría.

La demo local funciona contra su servidor local; no implementa sincronización con ERPNext ni PWA offline.
