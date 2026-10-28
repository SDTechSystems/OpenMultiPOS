# Construcción del servidor WSL

Trabajo de distribución en desarrollo. Estos archivos son herramientas de construcción; todavía no constituyen el instalador final ni inician un servidor operativo.

La base elegida es una distribución WSL2 Ubuntu 26.04 x64 nueva y exclusiva. Microsoft admite distribuir su filesystem como un archivo `.wsl` y ejecutar una configuración inicial mediante `wsl-distribution.conf`: [guía oficial](https://learn.microsoft.com/en-us/windows/wsl/build-custom-distro). Requiere WSL 2.4.4 o posterior. Los requisitos finales de Windows, almacenamiento y portabilidad se comprueban antes de entregar el paquete.

`build-image.sh` exige root, Ubuntu 26.04 x64, el marcador `/etc/openmultipos-build-environment`, una exportación pública del repositorio en `/opt/openmultipos/source` con metadatos Git y una distribución sin montajes Windows ni interoperabilidad. Instala herramientas del sistema y crea un usuario Linux bloqueado sin sudo. Ejecuta las dependencias y assets como ese usuario, con un entorno vacío salvo PATH, HOME e idioma. Los servicios no se inician durante la construcción.

El constructor reutiliza `scripts/prepare-bench.py`, que verifica los tres commits de `upstream.lock.json`. Node 24.22.0 se obtiene de nodejs.org y se verifica contra su SHA256; Bench 5.29.1 y Yarn 1.22.22 están fijados. Los paquetes Ubuntu y dependencias transitivas deben registrarse en el manifiesto de la imagen final. Este procedimiento no promete igualdad binaria entre reconstrucciones.

Nunca usar una distribución que contenga datos operativos ni exportar una instalación del propietario. La imagen compartida debe contener herramientas, código, assets y avisos de licencia, sin un sitio Frappe, base comercial ni credenciales. Los secretos y el sitio se crearán durante la primera ejecución privada.

Antes de exportar, ejecutar el control `image_contract.py` con la raíz de la imagen. Rechaza directorios de sitio, esquemas MariaDB ajenos al sistema, credenciales en la configuración común y contraseñas Linux reutilizables. Es una comprobación necesaria, no una auditoría completa del filesystem. La revisión de contenido, sanitización, manifiesto y ensayos de instalación/actualización/recuperación siguen siendo obligatorios.

La construcción limpia no acredita todavía el arranque del servidor ni su uso desde Windows. El manual de operación e instalación se actualizará con las acciones verificadas cuando estén disponibles.
