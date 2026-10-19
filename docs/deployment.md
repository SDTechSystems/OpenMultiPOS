# Despliegue

**No hay despliegue productivo validado en esta iteración.** La demo es local y no debe publicarse en red. No se creó servicio externo, contenedor ni instancia ERPNext.

La ruta prevista es Frappe/ERPNext v16 autohospedado con X POS web y la app OpenMultiPOS separada. SHAs y restricciones runtime están en upstream.lock.json; comandos candidatos en development.md. No se publica un docker-compose supuestamente funcional sin probarlo.

Antes de uso real: fijar versiones de base de datos, Redis, Node, Bench e imagen OS; validar instalación, TLS, sesiones, permisos negativos, stock/pagos, idempotencia concurrente, colas y respaldo/restauración aislada. Generar secretos solo en el destino privado y mantener fuera del repositorio. Registrar el commit exacto y resultados del sitio de ensayo.

Actualizaciones: backup restaurable y ensayo de migraciones en staging, revisar cambios upstream, actualizar lock tras pruebas. No cambiar automáticamente de rama a latest en producción. Hardware se prueba por modelo/controlador/firmware y no se deduce del éxito de CI.
