# Puerto fiscal futuro

Estado: desactivado. El MVP solo produce recibos internos de demostración/operación según su backend.

Contrato conceptual versionado: validate_configuration, prepare_document, submit(document, idempotency_key), check_status, fetch_representation y handle_error. Se añadirá un proveedor real como módulo independiente, con estados fiscales distintos a estados de venta.

El proveedor implementado en el scaffold devuelve `not_configured` y `issued: false`. No realiza conexiones de red, no pide certificados, no inventa CUFE ni QR fiscal, no contabiliza y no descuenta inventario. No se afirma cumplimiento normativo. La investigación regulatoria y habilitación requiere un encargo posterior con fuentes vigentes.
