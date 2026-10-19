# Impresión y lectores: matriz de pruebas físicas

Referencia del brief: Jaltech POS JAL 58M, código 40163. No se recibió un archivo de imagen independiente en esta sesión. La ficha del fabricante confirma papel de 57 mm, 203 DPI, 384 puntos, USB y corte manual; ESC/POS es una declaración del fabricante, no un ensayo de integración. [Fuente](https://jaltechsas.com/product/impresora-jaltech-pos-58-mm/).

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
