# Construcción del servidor WSL

Trabajo de distribución en desarrollo. Estos archivos son herramientas de construcción; todavía no constituyen el instalador final ni inician un servidor operativo.

La base elegida es una distribución WSL2 Ubuntu 26.04 x64 nueva y exclusiva. Microsoft admite distribuir su filesystem como un archivo `.wsl` y ejecutar una configuración inicial mediante `wsl-distribution.conf`: [guía oficial](https://learn.microsoft.com/en-us/windows/wsl/build-custom-distro). Requiere WSL 2.4.4 o posterior. Los requisitos finales de Windows, almacenamiento y portabilidad se comprueban antes de entregar el paquete.

`build-image.sh` exige root, Ubuntu 26.04 x64, el marcador `/etc/openmultipos-build-environment`, una exportación pública del repositorio en `/opt/openmultipos/source` con metadatos Git y una distribución sin montajes Windows ni interoperabilidad. Instala herramientas del sistema y crea un usuario Linux bloqueado sin sudo. Ejecuta las dependencias y assets como ese usuario, con un entorno vacío salvo PATH, HOME e idioma. Los servicios no se inician durante la construcción.

El constructor reutiliza `scripts/prepare-bench.py`, que verifica los tres commits de `upstream.lock.json`. Node 24.22.0 se obtiene de nodejs.org y se verifica contra su SHA256; Bench 5.29.1 y Yarn 1.22.22 están fijados. Los paquetes Ubuntu y dependencias transitivas deben registrarse en el manifiesto de la imagen final. Este procedimiento no promete igualdad binaria entre reconstrucciones.

Nunca usar una distribución que contenga datos operativos ni exportar una instalación del propietario. La imagen compartida debe contener herramientas, código, assets y avisos de licencia, sin un sitio Frappe, base comercial ni credenciales. Los secretos y el sitio se crearán durante la primera ejecución privada.

Antes de exportar, ejecutar el control `image_contract.py` con la raíz de la imagen. Rechaza directorios de sitio, esquemas MariaDB ajenos al sistema, credenciales en la configuración común y contraseñas Linux reutilizables. Es una comprobación necesaria, no una auditoría completa del filesystem. La revisión de contenido, sanitización, manifiesto y ensayos de instalación/actualización/recuperación siguen siendo obligatorios.

La construcción limpia no acredita todavía el arranque del servidor ni su uso desde Windows. El manual de operación e instalación se actualizará con las acciones verificadas cuando estén disponibles.

## Inicialización privada y control

`first_run.py` prepara un sitio nuevo dentro de la distribución dedicada. Recibe la contraseña inicial mediante una entrada oculta o stdin, genera las claves locales, registra el intento en un archivo root privado y retira la cuenta temporal de instalación de MariaDB. Un sitio previo sin registro de propiedad se conserva y se rechaza. Repetir una instalación completada conserva su contraseña y sus datos. La acción `recover` conserva el esquema anterior y mueve sus archivos fuera del directorio de sitios antes de generar otro intento. Exige la identidad y contraseña de base registradas y rechaza una instalación completada, cuentas personales, archivos subidos o registros comerciales. No borra bases de datos. Conserva hasta tres intentos; después exige revisión local. Un intento de recuperación interrumpido se puede retomar con `setup`. La integración del botón de recuperación en Windows sigue pendiente.

El servidor usa MariaDB sin TCP, dos Redis por sockets privados y una cola con AOF. Gunicorn, worker, scheduler y realtime se ejecutan sin root; Nginx escucha únicamente en `localhost:8089`. El proxy conserva el host del navegador y selecciona el sitio interno por un encabezado fijo. No se activa acceso remoto por este procedimiento.

La acción `serve` mantiene abierta una sesión de control de WSL, necesaria porque los servicios systemd por sí solos no mantienen activa la distribución. Espera `stop` o el cierre de stdin y detiene los servicios de forma ordenada. El controlador Windows pendiente deberá conservar esa conexión mientras el servidor esté activo. `start` solo inicia y comprueba servicios; no sustituye una sesión persistente. `status` informa si existe una instalación completada, no certifica salud operativa.

Una inicialización aprobada no marca como completado el asistente nativo de ERPNext. El primer acceso exige terminarlo antes de abrir `/omp`, y después revisar la preparación de negocios, usuarios, inventario, recibos y recuperación. Los controles Windows y la experiencia completa de instalación todavía están en desarrollo.

## Controlador Windows

`windows/Server.cs` añade una ventana WinForms para importar la imagen verificada, preparar o recuperar el acceso inicial y mantener la sesión del servidor. La ventana muestra el estado y la ubicación de datos; ofrece inicio, parada, aplicación y manual. Conserva stdin del proceso WSL hasta detenerlo y espera su salida sin terminar procesos a la fuerza. Al cerrar un servidor activo pide confirmar la desconexión de los demás equipos. Los secretos se envían por stdin UTF-8 y no se guardan en el registro del controlador.

El protocolo local 1 expone únicamente estado de instalación, disponibilidad de recuperación y número de intentos conservados. `serve --events` anuncia disponibilidad mediante un evento sin datos privados. El controlador rechaza una versión incompatible. La imagen complementaria deberá llamarse OpenMultiPOS-Server.wsl y coincidir con el SHA256 de server-image.json, schema 1. La importación conserva cualquier carpeta de datos ya existente y nunca ejecuta unregister.

El candidato compilado incluye código correspondiente y manual; la imagen sellada todavía no está incluida. La comprobación real Windows aprobó estado, transporte de texto Unicode/comillas por stdin, inicio con evento ready y parada mediante EOF en una copia QA. Las pruebas propias rechazan nombres de distribución ajenos, imágenes alteradas y manifiestos incompletos. La inspección visual/teclado no se completó porque el helper Computer Use no pudo inicializar su contexto WSL; sigue pendiente, junto con importación real del paquete y experiencia completa del instalador.
