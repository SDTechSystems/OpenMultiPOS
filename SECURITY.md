# Seguridad

Versión inicial de desarrollo. No usar con datos o transacciones reales hasta completar las puertas de integración descritas en docs/roadmap.md.

La demo escucha solo en 127.0.0.1. Su selector de usuario es una simulación, sin autenticación: cualquier persona con acceso local puede elegir Administrador demo. No exponer este servidor en red ni añadir datos reales. El token de proceso/origen y Host limitan llamadas web cruzadas; no sustituyen autenticación.

Para reportar un riesgo, contactar al mantenedor mediante los canales privados de GitHub disponibles en el repositorio. No incluir credenciales, documentos reales, certificados o información de clientes en issues públicos. Si no hay canal privado configurado, abrir un issue mínimo solicitando contacto sin detalles explotables.

Frappe aporta sesiones y permisos nativos. La extensión añade restricciones; todavía requieren integración en Bench. No hay puente de impresión abierto, pagos bancarios ni servicios DIAN.

El CLI nativo de impresión es optativo y local: solo recibe PBM acotado y una cola nombrada por el operador. No hay endpoint que acepte bytes ESC/POS desde el navegador. No reintentar un envío ambiguo sin revisar la cola. El modo de teclado US se limita a inputs seleccionados y no ejecuta ni abre contenidos escaneados.

## Privacidad de publicación

El repositorio y sus issues/PRs son públicos. Solo deben contener código, documentación técnica y ejemplos completamente ficticios. Nunca se publican información comercial real, archivos de entrada del propietario, nombres/contactos de clientes o proveedores, datos fiscales/bancarios, credenciales, fotos, capturas, tickets, respaldos o bases locales. Las marcas de demo y sus importes se inventan; no se derivan de catálogos reales.

`.gitignore` y el guard `scripts/check-public-files.py` bloquean formatos privados, ubicaciones de datos, rutas de usuario, claves/tokens reconocibles y correos no reservados para ejemplos. No imprimen valores encontrados. Activa los hooks locales con `git config --local core.hooksPath .githooks`: pre-commit revisa el índice completo y pre-push revisa el commit que se va a enviar. CI repite la revisión y no crea artefactos si falla. Nunca omitir estos controles para publicar material privado.

Estos controles detectan patrones comunes, no toda información personal/comercial en texto libre. Revisar siempre el diff y los archivos exactos antes de publicar. Cualquier recurso binario genuinamente necesario debe pasar una revisión explícita de privacidad/procedencia y ajustar la política; los documentos del negocio no son recursos del programa.
