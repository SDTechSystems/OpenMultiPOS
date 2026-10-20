# Desarrollo e instalación Frappe

## Entorno validado el 19/10/2026

Instalación local limpia: Ubuntu 26.04.1 en WSL2, Python 3.14.4, Node 24.22.0, Yarn 1.22.22, Bench 5.29.1, MariaDB 11.8.6 y Redis 8.0.5. Frappe 16.52.0, ERPNext 16.51.1 y X POS 2.12.0 se instalaron en los commits de `upstream.lock.json`, junto con la app OpenMultiPOS. Instalación de DocTypes y migración completadas.

Windows conserva el navegador POS, controladores de impresión y dispositivos. WSL ejecuta servidor, base de datos y herramientas. Se verificó que Chrome nativo de Windows llega al servidor WSL por `http://omp.localhost:8000`. Esto no sustituye ensayos del flujo POS completo ni de hardware.

Seguir [local-services.md](local-services.md) para instalar herramientas, preparar una instantánea del checkout en Linux y administrar el servicio web. El repositorio puede permanecer en Windows; Bench y sus dependencias residen en Linux. La instantánea no sincroniza automáticamente las ediciones posteriores.

## Crear un sitio local desechable

Con las aplicaciones ya preparadas mediante `scripts/prepare-bench.py` y los servicios en loopback:

```bash
cd "$HOME/.local/share/openmultipos/bench"
bench set-config -g redis_cache redis://127.0.0.1:6379/1
bench set-config -g redis_queue redis://127.0.0.1:6379/2
bench set-config -g redis_socketio redis://127.0.0.1:6379/1
bench new-site omp.localhost
bench --site omp.localhost install-app erpnext
bench --site omp.localhost install-app xpos
bench --site omp.localhost install-app open_multi_pos
bench --site omp.localhost migrate
```

`new-site` solicita credenciales locales. Usar una cuenta de instalación temporal de MariaDB, eliminarla después de crear el sitio y conservar las credenciales del sitio fuera de Git. En esta instalación no se cambió la autenticación de root. No reutilizar contraseñas de CI. Un sitio con datos propios nunca debe sustituirse mediante `--force` para repetir pruebas.

## Pruebas reales

```bash
bench --site omp.localhost set-config allow_tests True --parse
uv pip install --python env/bin/python -e './apps/frappe[test]'
bench --site omp.localhost run-tests --module open_multi_pos.integration.test_permissions --skip-before-tests
```

Resultado local: **9 pruebas de integración aprobadas**, con dos empresas/marcas, dos cajeros, permisos nativos por empresa, listas, métodos reales `frappe.client.get` y contexto OpenMultiPOS. Se comprueban Guest, acceso cruzado, perfiles desactivados, asignación nativa de usuarios, almacén de otra empresa, rechazo de escritura e instalación idempotente del rol. La suite usa los datos maestros estándar del setup ERPNext y entidades ficticias `OMP Test ...`.

Conservar `-e` al instalar extras de Frappe: una instalación no editable cambia la ruta de importación al wheel, que no contiene las fuentes frontend necesarias para `bench build`. En este Frappe `--parse` interpreta literales Python (`True`, no `true`); `--skip-test-records` está obsoleto y puede evitar que se ejecute la suite. CI reproduce instalación, migración y pruebas desde cero.

Con las nueve pruebas anteriores completadas y el servicio web activo en loopback, desde el checkout:

```bash
"$HOME/.local/share/openmultipos/bench/env/bin/python" scripts/test-xpos-http.py \
  --bench "$HOME/.local/share/openmultipos/bench"
```

Resultado: **19 pruebas HTTP reales**, con solicitudes v1/v2 autenticadas, usuarios de dos empresas, perfil de otra marca bajo la misma empresa, Sales Invoice/POS Invoice, permisos de campos y concurrencia del contador. La suite requiere `allow_tests`, crea exclusivamente borradores ficticios y aperturas POS de saldo cero que cancela, y restaura credenciales/roles temporales. Ejecutar solo en sitio desechable; no contra datos reales. CI compila `bench build --apps frappe,erpnext` antes de iniciar Gunicorn con dos workers/dos threads: las páginas HTML de error necesitan sus assets incluso cuando la prueba espera un 403. El sitio local ya incluye esos assets; un Bench nuevo preparado con `--skip-assets` debe compilarlos primero.

Las **40 pruebas sin Frappe** se ejecutan aparte mediante `python -m unittest discover -s tests -v`. Son pruebas del simulador/contratos; no sumarlas a las de Bench como si validaran stock productivo.

## Contexto de marca y límites

Configurar OMP Business Brand con Company/Warehouse/POS Profile coherentes. El cajero necesita `Sales User`, `OMP Cashier`, User Permissions nativas y autorización explícita de marca. No conceder roles contables para resolver una lectura de perfil.

Endpoint autenticado de lectura: `open_multi_pos.api.get_brand_context(brand=ID)`. Revalida permisos, perfil habilitado y pertenencia actual del almacén.

El probe `bench --site omp.localhost execute open_multi_pos.integration.audit_xpos.receipt_context_probe` usa ahora el método resuelto por los overrides. Devuelve `native_profile_access_denied=true` y `xpos_adapter_access_denied=true`. Las 19 pruebas HTTP comprueban además el dispatch real, incluyendo llamadas directas al adaptador. El cuerpo Python original upstream permanece intacto; los overrides no interceptan imports internos de otras aplicaciones.

Ver [matriz de APIs y límites](xpos-api-security.md). El cajero conserva lectura restringida; creación/reintentos y otras operaciones de factura X POS devuelven 403 incluso para managers. Antes de habilitarlas se necesita checkout nativo con unicidad atómica en BD, stock, pagos mixtos y cierres. Offline y restauración siguen pendientes. **Estas pruebas no certifican el resto de endpoints X POS.**
