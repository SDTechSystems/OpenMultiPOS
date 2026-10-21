# Respaldo y recuperación local

La operación usa Windows para abrir el programa y Ubuntu WSL para MariaDB, Redis, web y worker. El respaldo privado se guarda fuera del repositorio y del sitio. El temporizador se ejecuta a las 03:15, hora de Bogotá, con un pequeño retraso variable. Si el computador estaba apagado, ejecuta la copia pendiente cuando se inicia WSL y el temporizador. No puede copiar mientras el equipo está apagado.

## Abrir después de encender Windows

Ejecuta `scripts/start-openmultipos.cmd` desde el Explorador. Inicia MariaDB y Redis en Ubuntu, después web, worker y el temporizador de copia; abre Administración. Los servicios deben haberse instalado siguiendo [servicios locales](local-services.md). El lanzador no contiene credenciales. La distribución debe llamarse Ubuntu y tener configurado el usuario Linux predeterminado.

Si una venta, producto o entrada de inventario quedó pendiente, conserva el navegador y su almacenamiento. Inicia sesión con el mismo perfil y utiliza su opción de recuperación; conserva el identificador del intento. Una respuesta perdida no significa que la operación falló. No vuelvas a cobrar ni registres otra entrada para reemplazarla.

En **Ajustes > Respaldo y recuperación** puedes consultar la última copia verificada y el último ensayo correcto. Si no hay copia o tiene más de 36 horas, la pantalla indica que hace falta actualizarla. El estado no descarga datos ni muestra claves, archivos o nombres de bases.

## Crear y verificar una copia

Desde Ubuntu, con el programa instalado en las rutas de desarrollo documentadas:

```bash
systemctl --user start openmultipos-backup.service
systemctl --user status openmultipos-backup.service
systemctl --user list-timers openmultipos-backup.timer
```

Durante la copia se detienen temporalmente web, worker y scheduler si estaban activos. Al terminar, incluso ante error, se recuperan los servicios que estaban activos. No ejecutes simultáneamente `bench start`, otro servidor o consumidores adicionales fuera de estas unidades: esos procesos también podrían escribir. El modo `--offline` se reserva al instalador/CI, con todos los procesos detenidos; no detiene servicios por sí mismo.

La copia contiene SQL completo con las exclusiones de backup ignoradas, archivos públicos y privados, configuración con claves de cifrado, un manifest SHA256 y una instantánea de conciliación. Permisos: directorios 700 y archivos 600, en Linux, fuera de Git. Solo se acepta si las tablas y archivos no cambian durante la copia y las comprobaciones de stock/contabilidad no detectan diferencias. Un bloqueo evita dos copias simultáneas. Un directorio sin `manifest.json` no es una copia terminada.

El directorio predeterminado es `$HOME/.local/share/openmultipos/recovery`. `latest-backup.json` señala la copia aceptada. No se borran automáticamente copias antiguas; revisa espacio y conservación. Para otra ruta, ajusta la unidad y `omp_recovery_path` en la configuración privada del sitio. Evita rutas Windows, enlaces y espacios.

```bash
cd "$HOME/.local/share/openmultipos/bench"
env/bin/python -m open_multi_pos.operations --bench "$PWD" verify \
  --bundle "$HOME/.local/share/openmultipos/recovery/IDENTIFICADOR_DE_COPIA"
```

La verificación rechaza archivos faltantes, alterados, enlaces y permisos abiertos. El manifest detecta corrupción accidental; no autentica una copia de origen desconocido. No restaures SQL o archivos de terceros como si fueran una copia propia.

## Ensayar una restauración

El ensayo **siempre crea otro sitio y otra base**. No admite sobrescribir un sitio existente. Mantiene el clon en mantenimiento, con scheduler desactivado y correos silenciados. No lo conviertas directamente en el sitio de operación: contiene usuarios y documentos copiados, y su contraseña de instalación es distinta.

Necesita una cuenta de MariaDB con permisos para crear la nueva base/usuario. En una instalación con autenticación local por socket puede ejecutarlo un administrador del sistema con `sudo`; no cambies la autenticación de root para acomodar la herramienta. Cuando se usa contraseña, se lee de un archivo privado con permisos 600 mediante `--db-admin-file`, nunca de argumentos públicos. Ese JSON acepta `username`, `password` y, si corresponde, `host`, `port` o `socket`.

```bash
cd "$HOME/.local/share/openmultipos/bench"
sudo env/bin/python -m open_multi_pos.operations --bench "$PWD" restore-drill \
  --site omp-restore-a1b2c3d4.localhost \
  --bundle "$HOME/.local/share/openmultipos/recovery/IDENTIFICADOR_DE_COPIA"
```

Usa entre 8 y 32 caracteres hexadecimales nuevos después de `omp-restore-`. Una repetición con el mismo nombre se rechaza. El SQL se valida con Frappe y no se permite retroceder de versión. Los archivos se extraen con validación de sitio/ruta; se rechazan enlaces y dispositivos.

Se comparan 18 tablas completas: facturas, líneas, pagos, impuestos, entradas/lineas de stock, ledger de stock, GL, Bin, productos, precios, negocios, terminales, journals de cobro/cesta, marcas de abandono y aperturas/cierres. También se comparan todos los archivos y una prueba de descifrado de un secreto guardado cuando existe. La conciliación comprueba igualdad débito/crédito por voucher, existencias de Bin frente al ledger y facturas enviadas con asientos contables. No sustituye la conciliación bancaria ni certifica la configuración tributaria.

Un resultado correcto queda en `latest-restore.json` y dentro de `private/restore-result.json` del clon. Si falla, el clon permanece aislado y los detalles se conservan solo en archivos privados. Corrige la causa y repite con un nombre nuevo. El sitio original no se restaura ni modifica mediante este comando.

## Si se daña el sitio de operación

1. Detén el uso y conserva el navegador con sus intentos pendientes. No repitas cobros externos.
2. Verifica la copia y restaúrala en un sitio nuevo siguiendo el ensayo.
3. Revisa hasta qué fecha/hora contiene ventas, stock y GL. Una operación posterior al respaldo puede faltar aunque su pago externo haya ocurrido.
4. Concilia esas operaciones con sus comprobantes antes de reabrir. No reenvíes ciegamente intentos antiguos a una copia anterior: la copia podría no contener la clave que impedía duplicarlos.
5. Solo después decide con el administrador cómo cambiar la operación al sitio recuperado. La herramienta no redirige automáticamente Windows ni reemplaza el sitio original.

## Copia fuera del computador

La copia local permite recuperar errores del sitio, pero se pierde si se pierde el disco de WSL. Guarda copias verificadas en un destino privado separado. Protege el conjunto completo y sus claves con cifrado y acceso restringido; no envíes respaldos por GitHub, issues o capturas. Todavía no se configuró un destino externo en esta instalación. Ningún respaldo, manifest operativo ni log del ensayo forma parte del repositorio o de los artefactos públicos de CI.
