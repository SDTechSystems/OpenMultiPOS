# Despliegue

**No hay despliegue productivo validado.** Existe un sitio de desarrollo Frappe/ERPNext/X POS instalado en Ubuntu WSL, con base de datos y web en loopback. No se creó servicio externo ni contenedor local. La demo separada sigue siendo un simulador local.

La ruta es Frappe/ERPNext v16 autohospedado con X POS web y la app OpenMultiPOS separada. SHAs, restricciones y entorno de ensayo están en upstream.lock.json; instalación y resultados en development.md. CI incorpora servicios MariaDB/Redis por digest y una instalación nueva de las aplicaciones; no se presenta como receta de producción.

Antes de uso real: fijar versiones de base de datos, Redis, Node, Bench e imagen OS; validar instalación, TLS, sesiones, permisos negativos, stock/pagos, idempotencia concurrente, colas y respaldo/restauración aislada. Generar secretos solo en el destino privado y mantener fuera del repositorio. Registrar el commit exacto y resultados del sitio de ensayo.

Actualizaciones: backup restaurable y ensayo de migraciones en staging, revisar cambios upstream, actualizar lock tras pruebas. No cambiar automáticamente de rama a latest en producción. Hardware se prueba por modelo/controlador/firmware y no se deduce del éxito de CI.
