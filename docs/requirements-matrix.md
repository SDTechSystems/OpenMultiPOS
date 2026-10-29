# Matriz de requisitos y gaps

Estado de descubrimiento antes de implementar. “Existente” indica código upstream localizado, no aceptación superada. Evidencias y SHAs en [upstream.md](upstream.md). S/M/L son tamaños relativos.

| ID | Prioridad | Estado upstream | Evidencia | Gap | Riesgo | Esfuerzo | Prueba de aceptación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F01 | P0 | necesita configuración / extensión | Company, Warehouse, POS Profile | Añadir marca y usuarios; probar API cruzada | Alta | M | Dos marcas / misma entidad permitida |
| F02 | P0 | contrato HTTP de caja probado | Frappe roles, hooks propios y adaptadores X POS | 25 HTTP de seguridad, 20 checkout y navegador nativo; métodos y metadatos ajenos al contrato denegados | Crítica | L | Cajero no consulta ni escribe negocio ajeno; ampliar rutas exige revisión |
| F03 | P0 | existente / necesita configuración | ERPNext Item, Barcode, Item Price | Catálogo demo y plantillas; probar CSV/variantes | Media | M | Crear vela/mouse con modelos adecuados |
| F04 | P0 | integración en línea probada | Sales Invoice + Stock Ledger/GL nativos y caja web propia | Almacén, última unidad, rollback y E2E probados; otros movimientos pendientes | Crítica | L | Almacén correcto, stock exacto y sin duplicados |
| F05 | P0 | integración en línea probada | PK request, quote UNIQUE, Web Locks y tombstone | Respuesta perdida, recarga, retry, dos pestañas y solicitud tardía probados; devoluciones pendientes | Crítica | L | Reintento y cobros simultáneos una sola vez |
| F06 | P0 | integración en línea probada | Cash/Bank, POS Opening/Closing y pantalla propia | Mixtos, cambio y cierre visual probados; recuperación operativa ampliada pendiente | Alta | M | Efectivo + transferencia y cierre exactos |
| F07 | P0 | no verificado | Entrada de búsqueda X POS | Diagnóstico HID y terminador, prueba física | Media | M | Cinco códigos y QR ajeno sin navegar |
| F08 | P0 | extensión / equipo existente | Recibo compacto y preset confirmado | Página 48 mm, contenido 44 mm y altura medida; sin otros modelos | Media | M | Mantener configuración confirmada; fallo no duplica venta |
| F09 | P0 | integración web probada | Snapshot persistente y renderer escapado | Recibo/PDF 48/58/80 y permisos probados; papel/driver nativo pendientes | Alta | M | Dos marcas y reimpresión consistente |
| F10 | P0/P1 | requiere desarrollo / no verificado | X POS generación de barcode/QR declarada | QR comercial seguro y fallback de impresión | Media | M | Escanear salida real con dos lectores |
| F11 | P1 | no verificado | offlineStore.ts / syncEngine.ts / tests | Auditar seguridad offline y concurrencia con red real | Crítica | L | Dos reconexiones y conflictos visibles |
| F12 | P1 | existente / necesita configuración | ERPNext Customer, Supplier, Sales Order | Workflow de encargos/anticipos | Media | L | Reserva a entrega sin cobro duplicado |
| F13 | P1 | existente / necesita configuración | Purchase Invoice y valoración ERPNext | Costos importación y reporting | Alta | M | Margen estimado coherente con costo |
| F14 | P1 | existente / no verificado | Pricing Rule y bundles | Compatibilidad X POS y devoluciones | Alta | M | Promoción se aplica exactamente una vez |
| F15 | P1 | existente / necesita configuración | Reportes y backup Frappe | Exportaciones por rol y ensayo de restauración | Alta | L | Restaurar y conciliar en sitio aislado |
| F16 | P0 | extensión | Frontend X POS; demo propia | es-CO, teclado, responsive y accesibilidad | Media | M | Flujo teclado, móvil y 1366x768 |
| F17 | P1 | requiere desarrollo | Setup ERPNext/X POS | Guía replicable y diagnóstico sin hardware | Media | M | Usuario nuevo llega a recibo demo |
| F18 | P0 | no verificado / extensión | Frappe security y X POS permisos | Revisión negativa completa y dependencias | Crítica | L | IDOR/CSRF/XSS rechazados en integración |
| F19 | P3 | requiere desarrollo | Sin integración DIAN en la base | Solo contrato + proveedor desactivado | Alta | L | issued=false; ninguna red fiscal |


## Requisitos administrativos vigentes

La [hoja de ruta](roadmap.md) reemplaza la prioridad general de compatibilidad universal. F20-F28 se entregan en `/omp`: menú, perfiles, primer administrador, productos/entradas, cesta mixta, impresión para el equipo existente, herramientas nativas y manual visual. La relación negocio/entidad se configura durante el alta. Idioma, formato, moneda predeterminada y zona se editan en Ajustes; no se convierten documentos históricos.

Pruebas: `test-workspace-http.py` valida autorización, documentos/stock/GL, rollback conjunto, reintentos, marcas de abandono, contactos históricos y moneda contable. `test-workspace-browser.py` ejecuta formularios, recuperación por respuesta perdida, recorridos nativos, teclado, móvil y manual. Ver evidencia actualizada en [audit-report.md](audit-report.md). No se añaden nuevos ensayos de hardware ni se habilita offline o fiscal.

## Cierre P0 de recuperación

#7 añade ensayo HTTP con reinicio real, respaldos privados y restauración aislada con comparación de 18 tablas y archivos, prueba criptográfica y conciliación. El inventario fija 227 declaraciones HTTP de X POS; solo tres adaptadores autorizados siguen expuestos. Ver [recuperación](recovery.md) y [superficie HTTP](upstream-api-review.md). Los apartados de descubrimiento anteriores son históricos; los incrementos P1 de #7 se siguen en #19–#22 y la vista previa ERPNext en #18.
