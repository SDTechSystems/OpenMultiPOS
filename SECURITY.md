# Seguridad

Versión inicial de desarrollo. No usar con datos o transacciones reales hasta completar las puertas de integración descritas en docs/roadmap.md.

La demo escucha solo en 127.0.0.1. Su selector de usuario es una simulación, sin autenticación: cualquier persona con acceso local puede elegir Administrador demo. No exponer este servidor en red ni añadir datos reales. El token de proceso/origen y Host limitan llamadas web cruzadas; no sustituyen autenticación.

Para reportar un riesgo, contactar al mantenedor mediante los canales privados de GitHub disponibles en el repositorio. No incluir credenciales, documentos reales, certificados o información de clientes en issues públicos. Si no hay canal privado configurado, abrir un issue mínimo solicitando contacto sin detalles explotables.

Frappe aporta sesiones y permisos nativos. La extensión añade restricciones; todavía requieren integración en Bench. No hay puente de impresión abierto, pagos bancarios ni servicios DIAN.
