# Matriz de requisitos y gaps

Estado de descubrimiento antes de implementar. “Existente” indica código upstream localizado, no aceptación superada. Evidencias y SHAs en [upstream.md](upstream.md). S/M/L son tamaños relativos.

| ID | Prioridad | Estado upstream | Evidencia | Gap | Riesgo | Esfuerzo | Prueba de aceptación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F01 | P0 | necesita configuración / extensión | Company, Warehouse, POS Profile | Añadir marca y usuarios; probar API cruzada | Alta | M | Dos marcas / misma entidad permitida |
| F02 | P0 | existente / no verificado | Frappe roles; X POS auth.py | Auditar endpoints que usan ignore_permissions | Crítica | L | Cajero no consulta ni escribe negocio ajeno |
| F03 | P0 | existente / necesita configuración | ERPNext Item, Barcode, Item Price | Catálogo demo y plantillas; probar CSV/variantes | Media | M | Crear vela/mouse con modelos adecuados |
| F04 | P0 | existente / no verificado | Stock Entry y stock ledger ERPNext | Verificar modo POS, cierres y concurrencia | Crítica | L | Almacén correcto, stock exacto y sin duplicados |
| F05 | P0 | existente / extensión | X POS invoices.py / test_invoice_retry.py | Aislamiento y unicidad atómica todavía sin probar | Crítica | L | Reintento y cobros simultáneos una sola vez |
| F06 | P0 | existente / necesita configuración | ERPNext Mode of Payment y POS Closing | Configurar categorías; probar mixtos y cambio | Alta | M | Efectivo + transferencia y cierre exactos |
| F07 | P0 | no verificado | Entrada de búsqueda X POS | Diagnóstico HID y terminador, prueba física | Media | M | Cinco códigos y QR ajeno sin navegar |
| F08 | P0 | extensión / no verificado | X POS usePrintInvoice.ts | Perfiles genéricos, simulador, driver; hardware pendiente | Alta | M | 58/80 mm sin recortes; fallo no duplica venta |
| F09 | P0 | extensión | X POS receiptTemplate.ts / contexto Company | Marca independiente y snapshot histórico | Alta | M | Dos marcas y reimpresión consistente |
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
