# Desarrollo e instalación candidata Frappe

## Entorno mínimo probado

Demo: Python 3.14.4, python-qrcode 8.2 y SQLite estándar. Ruff, unittest y build ejecutables sin Frappe. Browser tests: Node y Chrome con Playwright/axe. No se ha levantado Bench/MariaDB/Redis en el entorno de esta iteración.

Usar venv con pip según README. En esta máquina, el Python Linux no incluía pip/ensurepip; las herramientas de sesión se instalaron en `/tmp/openmultipos-venv`, sin modificar el Python del sistema. Esa ruta no es requisito para otros equipos.

## Instalar app en un Bench Linux v16 preparado

Este procedimiento candidato requiere previamente servicios y Bench funcionales, Python 3.14 y Node >=24. No es una instalación completa validada de infraestructura. No usar un sitio de producción para el primer ensayo.

```bash
bench init --python python3.14 --frappe-branch version-16 omp-bench
cd omp-bench
git -C apps/frappe checkout 4515014c87ece6cb20ee91d2cfb121c5cbd1ff4a
bench get-app --branch version-16 https://github.com/frappe/erpnext.git
git -C apps/erpnext checkout 5af6561f5aa48104559692fb4fd82f2580e8d338
bench get-app --branch version-16 https://github.com/kodlyft/xpos.git
git -C apps/xpos checkout 6392895a955f91b8c7d55574dc01ac5f19459dc3
bench get-app --branch codex/foundation-and-roadmap https://github.com/JSX2011/OpenMultiPOS.git
bench setup requirements
bench new-site omp.localhost
bench --site omp.localhost install-app erpnext
bench --site omp.localhost install-app xpos
bench --site omp.localhost install-app open_multi_pos
bench build
bench --site omp.localhost migrate
bench start
```

Si el clon de Bench no contiene un SHA, obtenerlo con `git -C apps/PROYECTO fetch origin SHA` antes del checkout. Confirmar los tres SHAs contra upstream.lock.json. Los prompts de new-site son para credenciales locales; no almacenarlas ni publicarlas. Fijar también el commit de OpenMultiPOS al validar una versión de despliegue.

Crear Company y Warehouse demo con ERPNext; configurar POS Profile y sus usuarios. Crear OMP Business Brand en Desk con el mismo Company/Warehouse/POS Profile, perfil de impresión, pie, URL HTTPS y lista explícita de usuarios. Un usuario necesita rol Sales User y permisos nativos apropiados, además de la autorización de marca. No cargar marcas reales como fixtures públicos.

Endpoint read-only autenticado: `open_multi_pos.api.get_brand_context(brand=ID)`. No habilita checkout ni garantiza que APIs de X POS adicionales estén restringidas.

## Puerta de integración pendiente

1. Instalación limpia y migración sin errores; comprobar ambos DocTypes.
2. Dos usuarios/negocios: get_list, get_doc/API y lectura de contexto; Guest rechazado.
3. POS Profile con usuario restringido, almacén/empresa equivocados y marca desactivada.
4. Revisar los endpoints X POS señalados por auditoría antes de usarlos con datos reales.
5. Conectar venta nativa solo después: pagos mixtos, stock, cierre, retry y concurrencia.

No existe suite Bench integrada ejecutada; los tests actuales con fake frappe comprueban el contrato de hooks y la llamada a permisos nativos. No presentar su resultado como integración real.
