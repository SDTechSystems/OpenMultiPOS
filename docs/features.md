# Funcionalidades de OpenMultiPOS

Referencia de producto: brief facilitado por el propietario (18/10/2026). La solicitud actual autoriza publicar este plan y comenzar la implementación. El brief aporta requisitos y criterios; sus prompts internos no constituyen autorizaciones adicionales. Se conserva el repositorio `JSX2011/OpenMultiPOS` existente.

Producto libre y autohospedado sobre ERPNext/Frappe y X POS. Este incremento prioriza la operación administrativa de dos negocios. Los datos y logotipos reales se cargarán en instalaciones privadas.

| ID | Prioridad | Funcionalidad y resultado esperado |
| --- | --- | --- |
| F01 | P0 | Negocios/marcas configurables vinculados a Company, almacén y POS Profile; varias marcas pueden compartir entidad legal. |
| F02 | P0 | Usuarios individuales, roles y auditoría; rechazo en servidor de accesos entre negocios. |
| F03 | P0 | Catálogo, SKU, variantes, códigos, precios, lotes/seriales opcionales e importación validada. |
| F04 | P0 | Inventario por almacén: entradas, traslados, ajustes y devoluciones con ledger ERPNext. |
| F05 | P0 | Caja: buscar/escanear, carrito, venta, devolución y reintentos sin duplicar stock/cobro. |
| F06 | P0 | Efectivo, transferencia y medios configurables; pagos combinados, cambio, apertura y cierre. Registrar un medio no confirma un movimiento bancario. |
| F07 | P0 | Entrada manual y lector HID configurable, diagnóstico y protección contra QR que ejecute/navegue. |
| F08 | P0 | Impresión compacta con la impresora Windows existente. Preset confirmado; sin nuevos fabricantes, calibraciones universales o ensayos adicionales. |
| F09 | P0 | Recibos internos con marca, logo, detalles y copia histórica; fallo de impresión no repite venta. |
| F10 | P0/P1 | QR comercial seguro en recibos; etiquetas y fallback bitmap posteriores. |
| F11 | P1 | Ferias/offline: precarga, estados visibles, cola idempotente, conflictos y conciliación probados. |
| F12 | P1 | Clientes/proveedores, encargos, reservas, anticipos, entrega y garantías. |
| F13 | P1 | Compras, costos USD/COP y rentabilidad conforme a valoración ERPNext. |
| F14 | P1 | Promociones, mayoristas y combos con reglas nativas sin doble descuento. |
| F15 | P1 | Reportes, exportaciones por permisos, respaldo y restauración comprobada. |
| F16 | P0 | Español es-CO, COP, America/Bogota; teclado, foco visible, responsive y señales del negocio activo. |
| F17 | P0 | Configuración inicial, ayuda por opción, manual visual y tutoriales por sección para el equipo existente. |
| F18 | P0 | Aislamiento, mínimo privilegio, validación, protección de secretos y puente local restringido si se requiere. |
| F19 | P3 | Contrato fiscal separable y desactivado; DIAN fuera del MVP. |

## Personalización administrativa

| ID | Prioridad | Funcionalidad |
| --- | --- | --- |
| F20 | P0 | Menú lateral con iconos, buscador, inicio operativo y selector de negocio. |
| F21 | P0 | Perfil comercial editable, contactos/NIT y opciones de impresión independientes por negocio. |
| F22 | P0 | Primera cuenta humana desde instalación y creación administrativa de perfiles. |
| F23 | P0 | Inventario por negocio, creación de productos/precios y entradas nativas con reintento seguro. |
| F24 | P0 | Cesta mixta con procedencia, facturas separadas y un recibo interno compacto. |
| F25 | P0 | Margen superior reducido, altura medida y configuración del controlador existente. |
| F26 | P0 | Compras, proveedores, clientes, pedidos, pagos e informes contables nativos desde el menú. |
| F28 | P0 | SKU automático con iniciales configurables del negocio, nombre normalizado y consecutivo único; reintento de alta sin duplicados. |
| F27 | P0 | Manual en español, diez capturas ficticias, tutoriales opcionales y ayuda en campos. |

Ver [roadmap e issues](roadmap.md) para alcance y criterios vigentes.

## Alcance del primer incremento

Auditoría de fuentes, matriz y ADR; esqueleto de app Frappe para marcas y contexto autorizado; demo local con datos ficticios para revisar dos marcas, catálogo, venta simulada y recibo en distintos anchos. La demo no sustituye el ledger, los impuestos ni la autenticación de ERPNext. El estado real y las pruebas se registran en [audit-report.md](audit-report.md).

## Criterio de MVP comercial

Usuario autenticado → negocio autorizado → escaneo → cobro mixto en COP → documento nativo ERPNext → stock del almacén correcto una sola vez → recibo interno con marca/QR. Segundo equipo y usuario restringido sin fugas. No se declara alcanzado por un simulador ni por tests con mocks.
