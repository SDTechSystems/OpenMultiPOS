# Recibo interno v1

Entrada: snapshot de marca, líneas/precios, total, pagos/cambio en centavos y fecha UTC. Se escapa todo texto y se visualiza en COP/America/Bogota. Salida compacta: marca, estado demo/no fiscal, ID/fecha, artículos, total, pagos no cero, cambio si existe, agradecimiento y QR. No se imprimen diagnósticos ni configuración de perfil.

## Anchos que se deben distinguir

- `paper_mm`: rollo físico; no equivale al tamaño que anuncia el driver.
- `page_mm`: página lógica del controlador (opcional; por defecto rollo físico).
- `printable_mm`: ancho máximo útil del cabezal/controlador.
- `margin_mm`: margen de seguridad dentro de la página.
- Contenido: mínimo entre ancho útil y página menos dos márgenes.

En la cola POS-58/USB001 inspeccionada: rollo de referencia 57 mm, formularios del driver **58(48)**, página lógica 48 mm, contenido 44 mm y margen 2 mm por lado. El PDF anterior de 57 mm se recortaba al imprimir sobre 48 mm; centrarlo más no podía resolver esa discrepancia. Ahora html/body tienen ancho lógico fijo en pantalla y en impresión, tabla de ancho fijo y texto largo envuelto.

## Altura según contenido y límites del navegador

`receipt-print.js` espera fuentes/QR, mide altura al ancho final y configura dos longitudes finitas en @page, con 1 mm de guarda. El padding forma parte de la medición. Fallback de 150 mm; documentos largos se paginan a 280 mm por hoja, sin partir filas/pie cuando quepan. El descriptor anterior `size: ancho auto` no era válido.

El navegador genera un PDF corto; el diálogo físico puede volver a seleccionar un formulario fijo de 210/297/3276 mm. Esa selección está fuera de lo que CSS puede garantizar. No confundir tamaño del PDF con avance de papel real. Para máxima economía de rollo, usar un adaptador nativo validado por equipo.

## Diagnóstico nativo Windows / ESC-POS

`render-receipt-raster.cjs` renderiza solo una URL de recibo de la demo local al ancho útil, con márgenes internos, y produce PBM monocromático. Solo se elimina una eventual columna blanca extra causada por redondeo Chromium después de comprobar que no contiene tinta. No se recorta ni reescala contenido para ocultar un desbordamiento.

`windows_print.py` valida dimensiones/longitud, empaqueta raster en bloques de hasta 128 filas y envía un trabajo RAW a una cola local explícita con OpenPrinter/StartDocPrinter/WritePrinter. Inicialización/alineación, raster y un salto final; sin corte, cajón, servicios públicos ni reintento automático. `submitted` significa aceptación de cola, no prueba de papel. El helper no instala drivers ni cambia políticas de ejecución.

Se ensayó GS v 0 por elección explícita en POS-58: 384 × 711 puntos (~89 mm de contenido), trabajo 3, salida física confirmada por el propietario y foto inspeccionada: texto claro, columnas completas, márgenes equilibrados y sin cola larga. El modelo/firmware exacto sigue sin confirmar; no generalizar a todo Jaltech. El comando es heredado y Epson recomienda funciones gráficas nuevas para modelos nuevos; el adaptador se selecciona por capacidad verificada.

## QR y lector

QR comercial SVG local, HTTPS validado, cuatro módulos de silencio y geometría alineada a puntos. No QR fiscal ni CUFE, sin recursos remotos. Leer un QR con un escáner HID requiere también coherencia de distribución de teclado: el propietario obtuvo `httpsÑ--...` donde se codificó `https://...`. El modo US opcional interpreta códigos físicos en los campos de lector/búsqueda y permite comparar texto esperado sin navegar ni enviarlo al servidor. La distribución del sistema y el firmware no se modifican.

## Pruebas

- Browser: márgenes iguales y estables al entrar a modo print, ancho lógico correcto y sin overflow.
- PDFs de 48/58/80 mm: recibo corto de una página <130 mm; recibo de 50 artículos conserva todos los marcadores y pie final (4/4/3 páginas respectivamente).
- Encoder: reconstrucción exacta de 257 filas a través de bloques 128/128/1, sin pérdida, raster truncado/ancho excesivo rechazados.
- Hardware: salida nativa básica legible confirmada; QR y lector se registran separadamente en hardware-jaltech.md. Fotos del propietario no redistribuidas.

Fuentes: [API de impresión RAW de Microsoft](https://learn.microsoft.com/en-us/windows/win32/printdocs/sending-data-directly-to-a-printer), [referencia Epson GS v 0 y sus límites](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lv_0.html).
