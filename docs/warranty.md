# Garantías

En `/omp`, selecciona el negocio y abre **Garantías**. La sección registra reclamaciones de productos vendidos por la caja de ese negocio y su seguimiento. Usa el documento nativo **Warranty Claim** de ERPNext. Ver el [manual](manual.md#garantías) para el paso a paso.

## Qué hace

- Vincula cada reclamación a una venta de caja vigente del negocio activo, a una línea de esa venta, a su cliente y a su empresa.
- Registra fecha del reclamo, descripción, estado (Abierta, En revisión, Cerrada, Anulada), solución y notas de seguimiento. ERPNext registra la fecha de cierre.
- Recupera un alta con respuesta perdida sin duplicarla y bloquea un alta tardía después de resolver el intento.
- Detecta ediciones concurrentes desde OMP o desde el formulario nativo antes de guardar.

## Qué no hace

- No cobra, no reembolsa y no mueve existencias. Devoluciones y reemplazos siguen sus flujos propios.
- No calcula periodos de garantía, vencimientos ni cobertura. Las reglas se definirán antes de automatizarlas.
- No gestiona órdenes de reparación o servicio pagadas, números de serie ni lotes. Quedan para un incremento separado.
- No transmite documentos fiscales.

## Permisos

Requiere un administrador del espacio con acceso al negocio. La migración concede al rol `OMP Administrator` lectura, creación, escritura e informe de Warranty Claim; no concede borrado. Los cajeros no acceden. El filtro de negocio y la empresa se comprueban en servidor en cada llamada.

## Pruebas

`scripts/test-warranty-http.py` ejecuta nueve pruebas HTTP sobre ERPNext real con ventas y productos ficticios: alta sin efectos contables ni de stock, reintento y contenido distinto, concurrencia, abandono y alta tardía, seguimiento y cierre, edición concurrente, fechas y líneas inválidas, negocio ajeno con la misma empresa, Guest, cajero, negocio desactivado y venta anulada. `scripts/workspace-smoke.cjs` añade el recorrido de navegador con respuesta perdida, recarga, cierre, teclado, 390 px y axe. Ejecutar solo en un sitio desechable con `allow_tests`.
