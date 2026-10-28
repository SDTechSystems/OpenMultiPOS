#!/bin/bash
# Build only inside a clean, dedicated Ubuntu WSL distribution.
set -euo pipefail
umask 022
export DEBIAN_FRONTEND=noninteractive
export PATH=/opt/openmultipos/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
source /etc/os-release
[[ $EUID == 0 && $ID == ubuntu && $VERSION_ID == 26.04 && $(uname -m) == x86_64 ]]
[[ -f /etc/openmultipos-build-environment && ! -d /mnt/c/Users ]]
[[ -d /opt/openmultipos/source/.git ]]
if id openmultipos >/dev/null 2>&1; then
    account_home=$(getent passwd openmultipos | cut -d: -f6)
    [[ ! -d $account_home/.local/share/openmultipos/bench/sites/omp.localhost ]]
fi
if [[ -e /usr/sbin/policy-rc.d ]]; then
    echo 'Ya existe policy-rc.d. Revisa la distribución de construcción.' >&2
    exit 1
fi
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 755 /usr/sbin/policy-rc.d
trap 'rm -f /usr/sbin/policy-rc.d' EXIT
systemctl mask --now mariadb.service redis-server.service nginx.service
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git xz-utils build-essential \
    pkg-config python3.14-dev python3.14-venv libmariadb-dev mariadb-server mariadb-client \
    redis-server libffi-dev libssl-dev libjpeg-dev zlib1g-dev libpango-1.0-0 libpangocairo-1.0-0 \
    fontconfig fonts-dejavu-core nginx
python3.14 - <<'CONFIG'
import configparser
config = configparser.ConfigParser()
config.read('/etc/wsl.conf')
assert not config.getboolean('automount', 'enabled')
assert not config.getboolean('interop', 'enabled')
CONFIG
if ! id openmultipos >/dev/null 2>&1; then
    [[ -z $(getent passwd 1000 || true) ]]
    useradd --create-home --uid 1000 --shell /bin/bash openmultipos
    passwd --lock openmultipos
fi
[[ $(id -u openmultipos) == 1000 ]]
if [[ ! -x /opt/openmultipos/node/bin/node ]]; then
    curl --fail --location --proto '=https' --tlsv1.2 \
        https://nodejs.org/dist/v24.22.0/node-v24.22.0-linux-x64.tar.xz -o /tmp/omp-node.tar.xz
    echo 'cc2f601cee82d9a5a233302fe307abc600727035fd7d2c3a3571755989e95008  /tmp/omp-node.tar.xz' | sha256sum --check --status
    mkdir -p /opt/openmultipos/node
    tar -xJf /tmp/omp-node.tar.xz -C /opt/openmultipos/node --strip-components=1
    rm /tmp/omp-node.tar.xz
fi
[[ $(node --version) == v24.22.0 ]]
npm install --global yarn@1.22.22
account_home=$(getent passwd openmultipos | cut -d: -f6)
runuser -u openmultipos -- env -i HOME="$account_home" LANG=C.UTF-8 PATH="$PATH" /bin/bash -s <<'APP'
set -euo pipefail
umask 077
base=$HOME/.local/share/openmultipos
mkdir -p "$base"
if [[ ! -x $base/tools/bin/bench ]]; then
    python3.14 -m venv "$base/tools"
    "$base/tools/bin/pip" install frappe-bench==5.29.1
fi
export PATH="$base/tools/bin:$PATH"
git config --global --add safe.directory /opt/openmultipos/source
if [[ ! -d $base/bench ]]; then
    python3.14 /opt/openmultipos/source/scripts/prepare-bench.py --bench "$base/bench" --sources "$base/sources"
fi
cd "$base/bench"
bench build --apps frappe,erpnext,xpos,open_multi_pos
# An image contains tools and sources, never a site or a database credential.
test ! -d sites/omp.localhost
APP
printf 'Dependencias y assets construidos. Falta preparar y validar el arranque privado antes de exportar.\n'
