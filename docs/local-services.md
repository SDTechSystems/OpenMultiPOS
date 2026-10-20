# Servicios locales de desarrollo (Ubuntu WSL)

La instalación se realiza en Ubuntu, dentro de WSL. No instalar Bench sobre el Python de Windows ni colocar su entorno en una carpeta Windows con espacios. El checkout del proyecto puede permanecer en Windows; `scripts/prepare-bench.py` exporta una instantánea de desarrollo a Linux, sin mover el repositorio.

## Dependencias

Según la [instalación oficial de Frappe](https://docs.frappe.io/framework/user/en/installation), comprobar requisitos contra los commits de `upstream.lock.json`.

```bash
sudo apt-get update
sudo apt-get install -y build-essential pkg-config python3.14-dev python3.14-venv \
  libmariadb-dev mariadb-server mariadb-client redis-server libffi-dev libssl-dev \
  libjpeg-dev zlib1g-dev libpango-1.0-0 libpangocairo-1.0-0
```

Node debe ser >=24. En la instalación local se usó el binario oficial Node 24.22.0 para Linux x64, contrastado con su SHA256 oficial, bajo `/opt/openmultipos/node24`, con enlaces en `/usr/local/bin`. El Node 22 de Ubuntu no satisface este proyecto. Yarn está fijado a 1.22.22. No sobrescribir instalaciones ajenas al repetir el procedimiento.

```bash
python3.14 -m venv "$HOME/.local/share/openmultipos/tools"
"$HOME/.local/share/openmultipos/tools/bin/pip" install frappe-bench==5.29.1
# Añadir el directorio tools/bin a PATH, o enlazar bench, uv y honcho en ~/.local/bin.
sudo systemctl enable --now mariadb redis-server
node --version
yarn --version
bench --version
systemctl is-active mariadb redis-server
```

MariaDB y Redis escuchan solo en loopback; no se abrieron puertos de Windows ni reglas del firewall. No habilitar acceso remoto a la base de datos. En este sitio se configuraron explícitamente las bases lógicas Redis 1 (cache/socketio) y 2 (cola) del servicio instalado, según development.md. Un Bench sin esa configuración genera sus propios puertos Redis.

En PowerShell se pueden iniciar los servicios de esta distribución con:

```powershell
wsl -d Ubuntu -u root -- systemctl start mariadb redis-server
```

## Preparación reproducible

Desde el checkout del proyecto, con Python 3.14 y las herramientas anteriores en PATH:

```bash
python3 scripts/prepare-bench.py \
  --bench "$HOME/.local/share/openmultipos/bench" \
  --sources "$HOME/.local/share/openmultipos/sources"
```

El script exige un destino Bench nuevo, verifica cada SHA antes de instalar, no actualiza un checkout existente y copia únicamente fuentes del repositorio que Git no ignora. La instantánea local no sigue automáticamente ediciones posteriores. Para repetir una instalación limpia, usar otros directorios; no borrar un Bench con datos. El script prepara aplicaciones y dependencias, pero no crea sitios ni credenciales, ni instala servicios del sistema.

Crear un sitio de pruebas siguiendo [development.md](development.md). Las contraseñas se generan localmente y permanecen fuera de Git. No cambiar la autenticación del usuario root de MariaDB para acomodar la aplicación; usar una cuenta de instalación local temporal y eliminarla al terminar.

## Cajeros

El perfil de usuario necesita `Sales User` para las lecturas nativas de Company/Warehouse y `OMP Cashier` para leer exclusivamente los perfiles POS autorizados. `Sales User` por sí solo no tiene lectura de POS Profile en el commit ERPNext fijado. No conceder `Accounts User` como solución: es un rol más amplio.

OpenMultiPOS instala un permiso de solo lectura para `OMP Cashier`, conserva los permisos nativos de otros roles y restringe listas y documentos POS Profile para ese rol por marca habilitada, lista de acceso y `applicable_for_users`. Configurar también User Permissions nativas por Company/Warehouse. Los hooks restringen permisos; nunca sustituyen la autorización nativa.

Pruebas reales, separadas de los contratos sin Frappe:

```bash
cd "$HOME/.local/share/openmultipos/bench"
bench --site omp.localhost set-config allow_tests True --parse
bench --site omp.localhost run-tests \
  --module open_multi_pos.integration.test_permissions \
  --skip-before-tests
```

Este comando crea exclusivamente entidades ficticias `OMP Test ...` en el sitio de pruebas. Nunca ejecutarlo en un sitio de operación. Un resultado favorable cubre esos permisos y esa instalación; no certifica los endpoints adicionales de X POS ni checkout, stock o sincronización.

## Web desde Windows

La plantilla `examples/systemd/openmultipos-web.service` inicia Gunicorn y los assets del sitio en `127.0.0.1:8000`, sin depurador interactivo. Está instalada como servicio del usuario en esta máquina. Desde Ubuntu:

```bash
systemctl --user start openmultipos-web
systemctl --user stop openmultipos-web
systemctl --user restart openmultipos-web
journalctl --user -u openmultipos-web -n 30
```

Abrir [el sitio local](http://omp.localhost:8000/login) en Chrome/Edge de Windows. Se comprobó conexión desde Chrome Windows y login HTTP de Administrator. La contraseña generada permanece en `$HOME/.local/share/openmultipos/private/development-credentials.json`, con permisos 600, fuera del repositorio. No copiarla a documentación o issues.

Para instalar la plantilla en otro equipo, copiarla a `~/.config/systemd/user/`, ajustar las rutas si corresponde y ejecutar `systemctl --user daemon-reload` y `systemctl --user enable --now openmultipos-web`. No ejecutar `bench start` simultáneamente: usa el mismo puerto web. Este servicio sirve únicamente la web local; no representa una instalación de producción con workers, scheduler, TLS y supervisión completos.

Al compilar solo la versión web de X POS, se usó `CYPRESS_INSTALL_BINARY=0 ELECTRON_SKIP_BINARY_DOWNLOAD=1 bench build --production`. Así se evita descargar ejecutables de escritorio/pruebas que no participan en ese build. Las dependencias JS sí se instalan; los ensayos Electron no se dan por realizados.
