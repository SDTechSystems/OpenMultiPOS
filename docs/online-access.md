# Usar los mismos datos desde varios computadores

La instalación principal vive en el computador Windows que hace de servidor. Todos los computadores abren ese mismo sitio y guardan en su base de datos. No se necesita exportar ventas ni sincronizar archivos entre cajas. Una operación confirmada aparece al actualizar la consulta en el otro computador.

El servidor debe permanecer encendido, conectado a internet y con OpenMultiPOS iniciado. Si se suspende, reinicia o pierde internet, los demás computadores pierden acceso hasta que vuelva. La aplicación todavía requiere conexión para operar.

## Preparar el acceso privado

La opción propuesta es una red privada Tailscale y HTTPS mediante Tailscale Serve. Requiere instalar Tailscale y autorizar los equipos. Serve permite acceso dentro de esa red privada; la configuración aún debe verificarse en esta instalación antes de usar datos reales. Consulta las [instrucciones oficiales de Serve](https://tailscale.com/docs/features/tailscale-serve) y su [referencia de comandos](https://tailscale.com/docs/reference/tailscale-cli/serve).

1. Instala Tailscale en el servidor Windows y en cada computador autorizado. Inicia sesión con cuentas personales y protege el acceso a esas cuentas con autenticación multifactor.
2. Autoriza solamente los usuarios y equipos del negocio. En la política de acceso, permite a esos usuarios llegar al puerto HTTPS del servidor. Revisa las reglas existentes, porque una regla general anterior puede seguir concediendo más acceso.
3. Inicia OpenMultiPOS y comprueba el acceso local. Conserva MariaDB, Redis y el backend en loopback. No abras sus puertos en el router.
4. Prepara un proxy local que seleccione el sitio Frappe correcto, sirva sus recursos y envíe las cabeceras de HTTPS. Define la URL externa en `host_name`. La URL externa de Tailscale tiene otro nombre de host; apuntar Serve directamente al servidor de desarrollo no acredita una configuración correcta de Frappe. Ver [despliegue](deployment.md).
5. Con el proxy local verificado, ejecuta `tailscale serve --bg http://127.0.0.1:PUERTO_LOCAL` en el servidor. Sustituye `PUERTO_LOCAL` por su puerto. Sigue el enlace que ofrece Tailscale para habilitar HTTPS si hace falta. Guarda la dirección HTTPS que muestra `tailscale serve status`.
6. Abre esa dirección con `/omp` en cada computador autorizado e inicia sesión con su cuenta de OpenMultiPOS. Tailscale autoriza el acceso a la red; OpenMultiPOS conserva su propio inicio de sesión y permisos.

No actives Tailscale Funnel para este acceso privado. No compartas el usuario Administrator ni copies contraseñas, bases de datos o archivos del sitio a GitHub.

## Comprobar antes de operar

Usa datos ficticios en un sitio de aceptación. Comprueba inicio/cierre de sesión, recursos de pantalla, carga de archivos permitidos, vista previa de recibo y permisos desde el segundo computador. Registra una venta ficticia una sola vez y comprueba desde el otro equipo su factura y existencias. Desconecta el segundo equipo de la red privada y comprueba que ya no puede acceder. Verifica también el arranque después de reiniciar Windows.

Cada persona usa su propia cuenta y terminal. Resuelve un cobro pendiente desde el mismo navegador y usuario antes de cambiar de computador: la clave local de recuperación no viaja entre equipos. No repitas el cobro desde otra caja porque la primera dejó de responder. Consulta los documentos guardados y el estado del intento.

La impresión usa el controlador del computador desde el que imprimes. El servidor no imprime automáticamente en la caja remota. Conserva el preset de la impresora ya configurada.

## Respaldo y recuperación

El acceso compartido no es un respaldo. Mantén la copia privada diaria y una copia cifrada en otro dispositivo o destino privado. Guarda también la clave de cifrado que requiere Frappe y prueba una restauración. Sigue [recuperación](recovery.md), incluido el procedimiento para detener escrituras y conciliar documentos.

No sincronices en vivo el disco WSL, los archivos de MariaDB ni una carpeta Bench mediante OneDrive, Dropbox o Drive. Si utilizas almacenamiento en línea para respaldos, sube copias completas y cerradas mediante el procedimiento de respaldo, con acceso privado y cifrado. GitHub conserva el código del programa; los datos comerciales permanecen en el servidor y sus respaldos privados.

Para retirar un computador, cierra sus sesiones de OpenMultiPOS y elimina su acceso a Tailscale. Antes de cambiar de servidor, resuelve los intentos pendientes, realiza una copia verificada y restaura en el nuevo servidor. Mantén una sola instalación operativa durante el traslado.
