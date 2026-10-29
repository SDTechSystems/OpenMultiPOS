# Distribución Windows y primera configuración

Requisito de entrega solicitado por el propietario: al completar y validar el alcance acordado, entregar una edición portable y una edición instalable que se puedan compartir, ambas con una primera configuración guiada. Seguimiento: [distribución Windows #37](https://github.com/SDTechSystems/OpenMultiPOS/issues/37) y [asistente inicial #38](https://github.com/SDTechSystems/OpenMultiPOS/issues/38).

Este documento registra los candidatos disponibles y el trabajo pendiente. Los paquetes actuales permiten aceptación privada; todavía no son las entregas finales ni acreditan un asistente integral terminado.

## Cliente Windows disponible para aceptación

El cliente 0.1.0 tiene ZIP portable e instalador por usuario. Abre el servidor compartido en el navegador y guarda únicamente su dirección en el perfil de Windows. El instalador registra el acceso en Inicio y la desinstalación en Aplicaciones. Conserva las preferencias del cliente y los datos del servidor al quitarlo. Los archivos reemplazados quedan como `.previous` para recuperar una actualización del cliente.

Estos paquetes no incluyen el backend ni completan las entregas #37/#38. Necesitan un servidor ya configurado, Windows 10/11 x64 con .NET Framework 4.8 y un navegador actualizado. Están sin firma. La instalación, actualización, desinstalación y uso en Windows limpio siguen pendientes de aceptación.

Construcción sin red en Linux, usando Mono y `markdown2` ya instalado con Frappe:

```bash
<bench>/env/bin/python scripts/build-windows-client.py --output <directorio-nuevo>
```

El script compila ambos ejecutables, prueba el contrato de direcciones, incorpora el manual sin conexión con imágenes verificadas contra el manifest y genera SHA256SUMS.txt. El ZIP incluye el código correspondiente del cliente y del instalador. El paquete empieza sin dirección privada, usuario ni contraseña. El cliente remoto exige HTTPS; permite HTTP solo para loopback y el nombre local existente. Las pruebas de compilación bajo Mono no sustituyen la aceptación de WinForms, accesos y registro en Windows.

## Servidor completo disponible para aceptación privada

`scripts/build-windows-server.py` genera el ZIP portable del servidor y el instalador por usuario de `windows/ServerInstaller.cs`. El paquete incluye el controlador, `OpenMultiPOS-Server.wsl`, `server-image.json`, manual sin conexión, `source.zip` y hashes. El instalador necesita la imagen y el manifiesto junto al ejecutable. Ambos formatos requieren Windows x64, .NET Framework 4.8, WSL2, virtualización habilitada y 30 GB libres. Preparar WSL puede pedir administrador, descargas y reinicio.

El constructor exige que la imagen, el manifiesto y el informe de auditoría coincidan. La imagen privada sellada de 1,5 GB corresponde a la revisión `3f6e2da`; la auditoría del archivo exportado encontró cero sitios, cero esquemas de aplicación y ninguna identidad reutilizable. No se puede publicar hasta completar la aceptación y la revisión de fuentes y licencias.

```bash
<bench>/env/bin/python scripts/build-windows-server.py --output <directorio-nuevo> --image <imagen-limpia.wsl> --manifest <server-image.json> --audit <informe-auditoria.json>
```

La edición portable exige extraer la carpeta completa. El instalador copia el programa en el perfil del usuario, crea el acceso de Inicio y registra la desinstalación en HKCU. Los datos WSL quedan separados, por defecto en `%LOCALAPPDATA%\OpenMultiPOS\Servidor`. Actualizar o desinstalar el programa conserva la distribución y sus datos. Los archivos reemplazados quedan como `.previous`; actualizar este paquete no migra el backend ni los sitios existentes.

En Windows real, `--verify-import` importó la imagen sellada de 1,5 GB en `OpenMultiPOS-PackageQA`. Otra distribución recién importada, `ImageQA`, aprobó `first_run.py setup` y la comprobación Windows `--verify-server`, con estado, transporte por stdin, inicio y parada del servidor. `--verify-installation` aprobó archivos, acceso directo, HKCU, actualización, rechazo de corrupción, desinstalación y conservación de un archivo de datos separado. Esta última prueba usó una imagen sintética pequeña y no recorrió la interfaz con la imagen real.

El candidato está sin firma. Siguen pendientes la aceptación visual y de teclado, el recorrido completo en Windows limpio y el cierre de fuentes y licencias. Estas comprobaciones no acreditan una entrega final ni su uso en producción.

## Ediciones y datos

| Edición | Resultado esperado | Evidencia necesaria |
| --- | --- | --- |
| Portable | Paquete extraíble con inicio/parada y acceso a la aplicación sin el checkout de desarrollo. Datos propios separados y ruta visible. | Ejecución en Windows limpio y prueba de traslado a una ruta admitida. Verificar qué componentes puede transportar y cuáles requieren preparación del equipo. |
| Instalable | Instalador Windows con preparación de componentes, accesos, actualización y desinstalación que conserve datos por defecto. | Instalación nueva, reinicio, uso, actualización con copia previa, recuperación y desinstalación en Windows limpio. |

El backend sigue siendo ERPNext/Frappe y el candidato del servidor incluye sus componentes en una distribución WSL2 `.wsl`. Antes de afirmar portabilidad, comprobar requisitos de WSL/virtualización, permisos, espacio, descargas y reinicios en Windows limpio. El operador debe poder completar el proceso sin comandos de desarrollo. La construcción limpia, el arranque privado y la recuperación inicial aprobaron en WSL. La imagen sellada, su importación y las comprobaciones nativas Windows descritas arriba ya están disponibles; siguen pendientes la aceptación visual y las pruebas completas de entrega. El paquete requiere preparar Windows y conservar varios archivos juntos.

Los artefactos compartidos empiezan con una instalación limpia y generan secretos nuevos. Nunca incluyen la base operativa, identidades, productos, contactos, cuentas, documentos, contraseñas, claves, respaldos o preferencias privadas del propietario. Trasladar una instalación con datos es una operación privada de recuperación, distinta de compartir el programa.

La entrega debe tener versión, hashes, dependencias fijadas, licencias/avisos y construcción reproducible. Evaluar firma del instalador y documentar su estado. Mantener separado el programa de los datos, conservar estos al desinstalar por defecto y documentar actualización/restauración. El alcance físico de impresión/lectura sigue siendo el equipo ya configurado.

## Idioma del asistente nativo

La primera pantalla de ERPNext propone el idioma configurado del sitio mediante una extensión soportada. En el ensayo de instalación nueva, la configuración es produjo Español. Puedes cambiarlo: la extensión respeta la selección conservada por el asistente nativo. No sustituye sus validaciones ni completa pasos por su cuenta.

## Diseño del asistente

Se aplican onboard, frontend-design, accessibility y unslop. El [contexto visual existente](design-context.md) ya define audiencia y estilo: administradores con poco tiempo, tareas comprensibles, navegación azul, formularios legibles y ayuda en el lugar de uso. No se rediseña el producto como una portada comercial.

El primer resultado útil es configurar un negocio, agregar un producto con SKU y existencias correctas y revisar su recibo antes de una venta explícita. La experiencia asumida es administrativa, sin conocimientos del entorno de desarrollo; debe comprobarse con usuarios al implementar. No se inventa un tiempo de finalización antes de medirlo.

| Etapa | Qué hace la persona | Cuándo puede continuar |
| --- | --- | --- |
| Preparar el equipo | Revisa requisitos, ubicación de datos y componentes; resuelve permisos o reinicios indicados. | Los servicios necesarios responden y los errores tienen una acción concreta. |
| Crear acceso propio | Crea el primer administrador con credenciales nuevas mediante un arranque local seguro. | La primera cuenta se reclama una sola vez; altas posteriores exigen administración. |
| Elegir preferencias | Confirma idioma, moneda y zona horaria; se proponen español latinoamericano, es-CO, COP y America/Bogota. | Se guardan valores válidos y se explica qué cambia para entidades nuevas. |
| Configurar negocios | Elige entidad compartida/separada, datos comerciales/NIT, contactos, prefijo SKU, almacén y medios de pago. | La configuración nativa es coherente y los datos quedan en la instalación privada. |
| Preparar inventario | Agrega o importa productos y decide cómo registrar existencias. | El propietario, SKU, código de barras, precio y stock se pueden revisar; no se duplica una recepción/compra. |
| Revisar recibo y equipo | Confirma ajustes existentes del lector/impresora y opciones de contacto por negocio; abre una vista previa. | Puede reconocer negocio, productos y contenido del recibo sin crear una venta de prueba en el ledger operativo. |
| Revisar y comenzar | Revisa accesos, ubicación de datos y respaldo/recuperación; abre caja cuando vaya a operar. | Los requisitos obligatorios están completos y quedan accesibles los pasos pospuestos y el manual. |

Cada etapa se divide en subpasos cortos. Mostrar progreso, Atrás/Siguiente, errores junto al campo y ayuda con palabras del operador. Pedir datos cuando hacen falta; ofrecer posponer elementos opcionales y volver desde Ajustes/Ayuda. Los requisitos de acceso, coherencia y contabilidad siguen siendo obligatorios antes de operar.

Guardar progreso real en servidor y recuperar el mismo intento tras un error, recarga o reinicio. No basta con una bandera local de "asistente visto". Repetir una acción no debe crear otra cuenta, entidad, producto o movimiento. Conservar las validaciones y el asistente nativo de ERPNext mediante extensiones soportadas; no marcar el setup como terminado sin realizar su configuración.

Las instalaciones existentes conservan su configuración y no reciben de nuevo el recorrido obligatorio. Los tutoriales opcionales son repetibles y respetan los mensajes descartados. Teclado, foco, avisos accesibles y adaptación de tamaño forman parte de la implementación.

## Condición de entrega

No declarar lista la distribución hasta probar ambas ediciones sin herramientas de desarrollo: primera ejecución, interrupción y reanudación, errores, primera cuenta única, negocios con entidad compartida/separada, configuración completa, reinicio, actualización, copia/restauración y conservación de datos al desinstalar. Las pruebas usan fixtures inventados; la revisión humana de comprensión se registra cuando ocurra.

El manual visual debe explicar la instalación y cada etapa con capturas ficticias. La versión compartida debe recorrer este mismo asistente con datos nuevos de quien la recibe, sin heredar el negocio ni las credenciales del propietario.
