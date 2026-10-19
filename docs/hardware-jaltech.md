# Impresión y lectores: matriz de pruebas físicas

Referencia del brief: Jaltech POS JAL 58M, código 40163. El propietario compartió después una fotografía de la salida física; se inspeccionó sin redistribuirla. La ficha del fabricante confirma papel de 57 mm, 203 DPI, 384 puntos, USB y corte manual; ESC/POS es una declaración del fabricante, no un ensayo de integración. [Fuente](https://jaltechsas.com/product/impresora-jaltech-pos-58-mm/).

## Diseño para varias impresoras

| Perfil | Papel | Ancho útil de layout | Puntos de referencia | Corte | Estado |
| --- | --- | --- | --- | --- | --- |
| jaltech-jal58m | 57 mm | 48 mm | 384 | Manual | Configurado, sin ensayo físico |
| generic-58 | 58 mm | 48 mm | 384 | Ninguno solicitado | Ejemplo configurable, sin certificación |
| generic-80 | 80 mm | 72 mm | 576 | Ninguno solicitado | Ejemplo configurable, sin certificación |

Perfiles independientes del adaptador. Actualmente vista previa HTML y diálogo del navegador/driver. No se detectan dispositivos USB ni se envían comandos ESC/POS; ese adaptador se implementará solo si el controlador no basta. Anchos/puntos del perfil genérico no garantizan la capacidad de todos los modelos.

## Ensayo por combinación de modelo/firmware/OS/driver

- [ ] Registrar modelo exacto, interfaz, firmware, OS, driver, tamaño de rollo y área imprimible.
- [ ] Windows: instalar controlador del fabricante y hoja de diagnóstico del sistema.
- [ ] Elegir perfil, escala 100%, sin encabezados/pies de navegador, márgenes acordes al driver.
- [ ] Dos marcas, nombres largos, tildes, cantidades, totales COP; medir sin recortes.
- [ ] QR con margen de silencio: leer exactamente la URL ficticia con dos cámaras/lectores.
- [ ] Desconectar USB/agotar papel: comprobar que la venta no se repite y reintentar impresión.
- [ ] Reimprimir comprobante anterior tras cambiar la configuración de marca.
- [ ] Corte manual en JAL 58M; no solicitar corte/cajón sin capacidad comprobada.
- [ ] Repetir con otra marca/modelo y guardar resultados y foto autorizada fuera de datos privados.
- [ ] Linux/macOS: pendientes de ensayo, sin afirmar compatibilidad propia.

Lector de referencia JAL-PLUS 01 / 40213: confirmar modo HID y terminador Enter/Tab; escanear cinco códigos 1D/QR, foco, duplicados y entrada manual. La demo permite buscar por código con Enter; la validación física del lector queda pendiente. [Fabricante](https://jaltechsas.com/product/escaner-plus-1d-qr/).

## Ensayo de esta sesión en Windows

- Detectado controlador **POS-58** instalado y puerto **USB001**, inicialmente sin cola térmica. Se creó `OpenMultiPOS Demo POS58` sin cambiar la impresora predeterminada ni instalar software.
- La carpeta de driver aportada por el propietario se denomina `IMPRESORA TÉRMICA 58MM_40021_OCPP-586-U`, distinta de la referencia 40163/JAL 58M del brief. Modelo físico exacto y firmware siguen **sin confirmar**; no certificar JAL 58M a partir de este ensayo.
- Primera prueba: recibo ficticio renderizado a ~384 puntos, enviado vía PrintDocument/driver. **SALIDA FÍSICA CONFIRMADA por el propietario** con foto; texto pequeño con pérdida de trazos/borrosidad y pie muy cercano al borde. No se da por aprobado el criterio de legibilidad ni QR.
- Ajuste: texto mayor/reforzado, QR alineado a módulos enteros, raster sin interpolación y umbral blanco/negro en script diagnóstico, longitud de papel calculada con avance final.
- Segunda impresión automatizada: **NO EJECUTADA**, Windows bloqueó ejecución de archivo PowerShell por política local. No se cambió la política persistente; la versión nueva queda disponible mediante diálogo del navegador. Requiere comparación física.
- Escáner: diagnóstico visible preparado. El propietario efectuó un escaneo real: código alfanumérico de 10 caracteres capturado en ~70–80 ms y confirmado por él en pantalla. El primer diagnóstico agrupaba “botón o Enter”, por lo que el terminador exacto no se certifica; se refinó el campo para distinguir Enter/Tab. No se publica el código real. Lecturas QR y matriz de cinco códigos siguen pendientes.
- Ninguna foto, controlador binario, identificador de dispositivo o dato del propietario se añadió al repositorio.
