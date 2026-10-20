# Caja nativa en línea · API inicial

Estado: backend probado sobre los SHAs de `upstream.lock.json`, exclusivamente con datos ficticios. La pantalla de caja debe conectarse a este contrato. Las 14 rutas de factura X POS siguen bloqueadas; no se copió su motor ni se modificó core. Offline, devoluciones, reservas, lotes/seriales y emisión fiscal quedan fuera de este incremento.

## Configuración

Un administrador configura, en un sitio de ensayo:

1. Company, lista de venta y cuentas en COP; `POS Settings.invoice_type = Sales Invoice`. Se usan `is_pos=1`, `is_created_using_pos=1` y `update_stock=1`: ERPNext crea Stock Ledger Entry y GL Entry al enviar la factura. El cierre reconcilia, sin volver a contabilizar la venta.
2. Marca concedida, perfil activo exclusivo de esa marca y almacén hoja activo. Varias marcas pueden compartir empresa/almacén mediante perfiles distintos. FBR y cargos automáticos de entrega deben estar desactivados.
3. Cliente autorizado y precios Item Price de la lista del perfil; la lista del cliente no puede sustituirla. Se venden cantidades enteras de la unidad de inventario, aunque el artículo tenga otra unidad de venta configurada.
4. Medios Cash/Bank activos en el perfil y cuentas COP del tipo correspondiente. La cuenta de cambio coincide con la del efectivo utilizado. Transferencia es registro manual, sin confirmación bancaria.
5. Cajero con Sales User, OMP Cashier, User Permissions nativas, concesión de marca y applicable_for_users. Crear OMP POS Terminal con ese usuario/marca y habilitarla. Genera UUID y no permite reasignar usuario/marca; las terminales nuevas están deshabilitadas por defecto.

No se conceden Accounts User/Manager al cajero. OMP Cashier incorpora permisos nativos mínimos de lectura/creación/edición/envío de Sales Invoice y aperturas/cierres. Los hooks deniegan escrituras directas: solo una capacidad privada ContextVar, limitada a documentos construidos por el servicio durante esa solicitud, permite continuar con las comprobaciones nativas. No es una bandera del payload ni omite `check_permission`. El perfil sigue siendo de solo lectura.

## Contrato HTTP

Prefijos Frappe `/api/method/` y `/api/v2/method/`; métodos bajo `open_multi_pos.checkout`. Autenticación normal Frappe; el navegador debe conservar CSRF.

| Método | Verbo | Entrada |
| --- | --- | --- |
| `open_shift` | POST | `data: {terminal, balances: [{mode_of_payment, amount}]}`; todos los medios, incluido cero. Saldos idénticos recuperan apertura activa. |
| `quote` | POST | `data: {terminal, customer, items: [{item_code, qty}]}`; 1–50 líneas únicas, qty entero 1–10000. Rechaza campos extra como rate, warehouse, taxes o ignore_permissions. |
| `checkout` | POST | `data: {terminal, request_id, quote, payments: [{mode_of_payment, amount, reference_no?}]}`; UUID v4 canónico y quote devuelto por el servidor. |
| `get_status` | GET/POST | `terminal, request_id`. Devuelve factura y snapshot histórico. `not_found` exige conservar la misma clave al reintentar. |
| `shift_summary` | POST | `terminal, opening_entry`. Importes esperados por medio, incluidos saldo inicial y efectivo neto de cambio. POST serializa la lectura con la caja. |
| `close_shift` | POST | `data: {terminal, opening_entry, counts: [{mode_of_payment, amount}]}`; todos los medios. Conserva diferencias. Repetir conteos idénticos recupera el cierre; otros conteos producen 409. |

Importes como **strings decimales**, punto y hasta dos decimales, máximo 999999999.99; cero solo en apertura/conteo. No floats del cliente, crédito ni pago parcial. El cambio solo proviene del efectivo recibido. Validación propia usa Decimal y snapshot usa centavos; la conversión a float se limita a campos nativos de ERPNext.

La cotización vence en diez minutos. ERPNext calcula precios, impuestos y totales. Antes de cobrar se reconstruye una huella financiera que incluye cuentas y contexto; cambios de precio/configuración exigen volver a cotizar. No se acepta un total, descuento, tasa o almacén elegido por el cliente.

## Atomicidad y recuperación

Se revalidan terminal, usuario, marca y permisos nativos antes de buscar duplicados. La marca guardada en el journal también restringe lecturas documentales históricas: reutilizar un perfil no concede esas facturas a otra marca.

OMP Checkout Request tiene clave primaria SHA256 de terminal + UUID y restricción **UNIQUE sobre quote**. Otro UUID no puede cobrar la misma cotización. Claim, factura enviada, stock, GL y snapshot comparten la transacción de checkout, sin commits/rollbacks propios. Una excepción revierte también el claim. Los journals privados usan inserciones internas de campos construidos por el servidor; no conceden escritura al cliente ni omiten permisos sobre facturas.

Se bloquea el perfil para serializar apertura/cobro/cierre, y artículos/bins en orden estable para competir entre perfiles por un almacén. Stock insuficiente se rechaza incluso si la configuración global permite stock negativo.

Se añade el Custom Field estándar `POS Opening Entry.omp_checkout_revision`. Cada venta lo incrementa en su misma transacción. Comparar su lectura de snapshot con la lectura actual bloqueada detecta una vista REPEATABLE READ anterior a otra venta o cierre y devuelve 409. El mutex por sí solo no actualiza la vista de lectura; se detectó y corrigió mediante el ensayo concurrente. Los eventos de documento rechazan escritura directa del cajero incluso con un DocShare de escritura.

Ante **409**, pérdida de respuesta o error posterior al commit, consultar estado y reintentar la misma clave/payload; nunca crear otra transacción automáticamente. Frappe también puede fallar al encolar trabajo después del commit. Una venta completada se recupera después del cierre o expiración; una factura anulada produce conflicto. El servicio registra pagos, no cobra tarjetas ni verifica transferencias externas.

**Límite del cierre nativo:** ERPNext hace un commit interno antes de actualizar algunas asociaciones de facturas. No se presenta el cierre como completamente atómico. Un retry idéntico recupera el cierre y repara asociaciones de forma idempotente, sin enviar facturas ni mover stock. También se prueba una venta concurrente con cierre. La recuperación de otros fallos de infraestructura requiere ensayos posteriores.

## Recibo y evidencia

Snapshot persistente: marca, contexto, fecha UTC, líneas, impuestos, total, pagos, cambio, pie/QR y `fiscal_issued=false`. Editar la marca no cambia el recibo anterior; imprimir/consultar no repite venta. La presentación HTML, el botón web y el trabajo de impresión son el siguiente incremento; el API no confirma papel.

```bash
# Primero migrar, ejecutar las nueve pruebas Bench y activar web/worker.
# Solo sitio desechable con allow_tests.
"$HOME/.local/share/openmultipos/bench/env/bin/python" scripts/test-native-checkout-http.py \
  --bench "$HOME/.local/share/openmultipos/bench"
```

16 casos HTTP reales cubren stock/GL, impuestos, mixtos/cambio, cierre, UUID/payload/quote únicos, concurrencia/última unidad entre perfiles, permisos, expiración/precio cambiado, rollback por contabilidad congelada, capacidades sin fugas, fiscal desactivado y snapshot. Stock Entry, facturas y cierres ficticios se conservan como evidencia. Al terminar se restauran tokens/roles/configuración temporal y se deshabilitan perfiles/marcas/terminales de esta suite. Contratos sin Frappe y seguridad X POS se ejecutan por separado. No equivale a ensayo completo de pantalla POS, hardware o producción.
