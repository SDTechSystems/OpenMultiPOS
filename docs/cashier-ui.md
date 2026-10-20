# Caja autenticada en desarrollo

Abrir `/omp_pos` en el sitio Frappe, por ejemplo [caja local](http://omp.localhost:8000/omp_pos). Usa sesión y CSRF de Frappe; un visitante se redirige al login. Requiere `OMP Cashier`, terminal habilitada propia y permisos actuales de marca/empresa/almacén/perfil. Administrator configura esos documentos desde `/app`; su sesión no representa por sí sola una terminal de cajero.

## Preparar una terminal ficticia

Seguir [native-checkout.md](native-checkout.md): Sales Invoice, COP, almacén activo, actualización de stock, lista/precios y cuentas Cash/Bank. Configurar `System Settings.time_zone = America/Bogota` **antes de crear movimientos**: fechas y validación del día de apertura usan la zona del sitio. Configurar el **cliente de mostrador en POS Profile.customer**; esta pantalla inicial no cambia cliente ni crea artículos/clientes. Perfil exclusivo por marca, concesión explícita y terminal individual por usuario. Usar `Sales User` y `OMP Cashier` con User Permissions de Company/Warehouse. Para ver/imprimir recibos también se requiere permiso nativo de impresión de Sales Invoice y permiso POS de reimpresión cuando corresponda; no conceder roles contables como atajo.

La instalación de desarrollo conserva Bench en Linux y navegador/controlador en Windows. Las fuentes de la app deben copiarse a la instantánea Bench antes de `migrate`, limpiar cache y reiniciar web/worker. Los recursos de `public/` se sirven mediante `/assets/open_multi_pos/`; no requieren copiar ni recompilar core. Ver [local-services.md](local-services.md).

Después de ejecutar las suites Bench/HTTP, puede dejarse una terminal ficticia de revisión separada de las terminales temporales:

```bash
"$HOME/.local/share/openmultipos/bench/env/bin/python" scripts/setup-native-cashier-demo.py \
  --bench "$HOME/.local/share/openmultipos/bench"
```

Requiere `allow_tests` y los fixtures ficticios previos. Crea `omp-demo-cashier@example.invalid`, marca/perfil/terminal, cliente/lista COP y almacén de demostración separados; completa a 20 unidades el SKU ficticio `OMP-NATIVE-STOCK-A` mediante Stock Entry nativo. Conserva la contraseña al repetirlo. Guarda `cashier_user`, `cashier_password` y `cashier_terminal` en el archivo privado `$HOME/.local/share/openmultipos/private/development-credentials.json` con modo 600, preservando la credencial anterior de Administrator. No muestra contraseñas ni envía correos. Iniciar sesión con ese cajero, en otro perfil/ventana privada si Administrator ya está conectado.

## Recorrido

1. Iniciar sesión como cajero, seleccionar terminal y registrar saldo inicial de **todos** los medios.
2. Buscar nombre/código o escanear código de barras y Enter. Un único código exacto autorizado agrega el artículo; una búsqueda por nombre permite escoger. Cantidades enteras de la unidad de inventario. La opción **Lector con teclado US** interpreta códigos físicos únicamente en búsqueda; dejarla desactivada para escribir normalmente con otra distribución.
3. Cotizar con ERPNext. El servidor calcula precio, impuestos, stock disponible y total; modificar el carrito invalida la cotización. No hay catálogo/precio local ni cobro offline.
4. Registrar importes recibidos. Se acepta coma o punto decimal sin separadores de miles; se envían strings con dos decimales. Transferencia es un registro manual, sin verificación bancaria. Guardar venta solo después de confirmar el pago externo.
5. Mostrar el recibo guardado, cambiar perfil y solicitar impresión. Volver a cargar el recibo o abrir el diálogo no vuelve a crear factura ni GL/stock. El navegador no confirma papel ni incrementa automáticamente el contador de impresión.
6. Nueva venta libera la pantalla solo al conocer un resultado completado o un intento bloqueado sin factura. Resumen y cierre muestra importes esperados; registrar el conteo real por medio. ERPNext conserva las diferencias.

## Si se pierde la respuesta

Antes del POST, se guarda en localStorage el payload exacto: terminal, UUID, quote y medios/importes. No se guardan contraseña, token, catálogo, cliente ni recibo. La clave se separa por sitio y usuario. Web Locks evita crear otra operación al enviar desde dos pestañas del mismo origen/perfil de navegador; otros equipos, perfiles u orígenes no comparten ese bloqueo.

Una recarga recupera el estado servidor con el mismo UUID. Si no existe venta, la pantalla conserva el intento: **Reintentar el mismo intento** envía exactamente el mismo payload. Nunca genera otro UUID automáticamente ni repite un pago externo. Errores de precio, expiración, configuración o permisos también conservan el intento hasta resolverlo.

**Resolver sin crear venta** toma el bloqueo de perfil y espera la operación en curso. Si ya terminó, recupera factura/recibo. En otro caso escribe un tombstone único: solicitudes tardías de checkout quedan rechazadas, incluso con otro UUID para esa quote. Después puede iniciarse otra cotización. No cancela ni devuelve dinero externo: conciliar ese pago antes de volver a cobrar. Ante un conflicto concurrente, consultar estado y reintentar la resolución.

No borrar datos del navegador durante un intento incierto. Si se pierde el almacenamiento, un administrador debe consultar el journal/facturas antes de crear otra venta. La pantalla conserva un intento hasta **Nueva venta**; el historial navegable, recuperación entre equipos y una cola offline requieren otro incremento. Chrome/Edge actuales con almacenamiento y Web Locks habilitados son el entorno esperado.

## Evidencia y límites

`scripts/test-native-cashier.py` prepara fixtures ficticios, pasa credenciales efímeras al runner JS por stdin y restaura hashes/sesiones/configuración al terminar. E2E contra Bench/MariaDB real: cuatro facturas y cuatro SLE, GL, login cookie/CSRF, dos cajeros, escaneo físico simulado, mixtos/cambio, pérdida antes/después del commit, recarga, retry, dos pestañas, tombstone, cierre, rechazo cruzado y fallo de recibo sin otro cobro.

Chrome Windows pasó teclado, viewports 390/768/1366, axe y PDFs de una página a 48/58/80 mm. CI reproduce el recorrido con Chromium Linux y sitio nuevo. Capturas/PDF exclusivamente ficticios en `test-results/native-cashier/`, fuera de Git. Esto no acredita un lector físico, el driver ni papel: el siguiente P0 ensaya el snapshot nativo con los dispositivos Windows. Mantener datos ficticios mientras continúan auditoría upstream, backup/restauración y validación operativa. DIAN permanece desactivada.
