# Ediciones y propiedad de los datos

Compartir el programa no comparte una instalación ni concede acceso a sus datos.

| Edición                               | Para quién                                                   | Dónde se guardan los datos                                              |
| ------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| OpenMultiPOS · Servidor propio        | Quien necesita una instalación independiente para su negocio | En el computador donde instala el servidor, con sitio y secretos nuevos |
| OpenMultiPOS · Conectar a mi servidor | Las cajas y otros computadores de ese mismo negocio          | En el servidor cuya dirección escribe su usuario                        |

El paquete completo portable y OpenMultiPOS-Server-Setup son la edición Servidor propio. OpenMultiPOS-Client-Setup y el portable del cliente son Conectar a mi servidor. Estos nombres técnicos de archivo se conservan para las actualizaciones. Los títulos del instalador, la ventana y Aplicaciones de Windows indican su función.

## Instalar para otra persona

Entrega el paquete limpio Servidor propio. La persona instala el servidor en su computador y crea sus credenciales y negocios. No recibe conexión al computador del creador ni hereda su red privada, cuentas, copias o datos. localhost identifica el computador de esa persona; no es una dirección del creador.

Entrega el ZIP completo o la carpeta completa del instalador. El ejecutable OpenMultiPOS-Server-Setup necesita la imagen OpenMultiPOS-Server.wsl y server-image.json a su lado. El ejecutable pequeño por sí solo no instala un servidor independiente.

El programa publicado en GitHub es genérico. La instalación privada del propietario, sus datos y sus ajustes de conexión permanecen fuera del repositorio y de los paquetes. No hace falta mantener una copia distinta del código para cada negocio.

## Conectar varios computadores de un negocio

Prepara primero su Servidor propio y su acceso privado. En los demás computadores instala Conectar a mi servidor e introduce la dirección HTTPS autorizada de ese servidor. Una instalación nueva del cliente no trae una dirección remota. Cada persona entra con su cuenta de OpenMultiPOS.

Para cambiarla, abre Configurar.cmd en la carpeta del cliente. En el computador que aloja el servidor puedes usar http://localhost:8089. Cambiar la dirección solo cambia el destino de la conexión: no mueve, combina ni copia los datos de un servidor a otro. Resuelve los cobros pendientes antes de cambiar de servidor.

## Qué se puede compartir

Comparte únicamente los paquetes limpios y sus fuentes, licencias, manual y hashes correspondientes. No compartas connection.txt, el disco WSL con datos, sitios, respaldos, contraseñas ni configuraciones de red privada. El constructor toma las fuentes Windows registradas en Git y rechaza enlaces; los archivos locales no registrados no entran en esas fuentes. El control de publicación bloquea connection.txt aunque se agregue por error.

La aceptación en Windows limpio sigue pendiente. Estos candidatos todavía no están aprobados para producción o distribución pública.
