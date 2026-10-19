# Recibo interno v1

Entrada: instantánea al completar la venta, con marca/símbolo demo, almacén, cajero, fecha UTC, líneas y precios unitarios, total, pagos y cambio en centavos enteros. Visualización de fecha en America/Bogota y dinero COP. La marca de un recibo histórico no se lee de la configuración actual.

Salida: HTML escapado, sin scripts ni plantillas de usuario ejecutables. QR comercial SVG generado localmente con qrcode 8.2, HTTPS validado, borde de cuatro módulos y geometría alineada a puntos del perfil. Sin QR fiscal ni CUFE. No se cargan recursos remotos al generar el recibo.

Layout por perfil de papel/ancho útil/DPI; el controlador debe usar escala 100% y márgenes calibrados. Texto térmico reforzado y QR sin suavizado. El perfil Jaltech es una referencia, no un requisito. Otros anchos/modelos pueden añadirse al archivo JSON sin modificar el checkout.

Vista previa e impresión no crean ventas. El navegador solicita un diálogo y no certifica papel impreso. Contador y auditoría productiva de reimpresiones se implementarán con documentos reales en una fase posterior; la demo conserva solamente su snapshot.

## Papel compacto

Se quitaron filas con pago cero, leyendas de diagnóstico, nombre de perfil y metadatos opcionales extensos. Se conserva marca, estado demo/no fiscal, ID/fecha, líneas, total, pagos reales, cambio cuando existe, agradecimiento y QR. Importes enteros COP se muestran sin centavos innecesarios.

`receipt-print.js` mide el contenido tras cargar fuentes/QR y genera `@page` con dos longitudes explícitas (ancho y altura). El formato anterior `size: 57mm auto` no era válido y podía dejar activo el papel largo del controlador. Hay fallback finito de 150 mm; carritos largos se paginan con techo de 280 mm por página en vez de pedir metros de papel. Esto no equivale a soporte ESC/POS directo.

Validación: el recibo de un producto de diagnóstico resultó en **89 mm** de alto; PDF Chrome de **una página**, MediaBox 162 × 252 puntos (~57 × 89 mm). Smoke de navegador exige menos de 130 mm para el caso de una línea y tamaño CSS finito. La longitud física final todavía requiere comprobar que el controlador respeta el tamaño de página personalizado; si lo ignora, configurar un formulario corto en esa cola. No se cambió una política de seguridad para hacerlo.
