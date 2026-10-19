# Recibo interno v1

Entrada: instantánea al completar la venta, con marca/símbolo demo, almacén, cajero, fecha UTC, líneas y precios unitarios, total, pagos y cambio en centavos enteros. Visualización de fecha en America/Bogota y dinero COP. La marca de un recibo histórico no se lee de la configuración actual.

Salida: HTML escapado, sin scripts ni plantillas de usuario ejecutables. QR comercial SVG generado localmente con qrcode 8.2, HTTPS validado, borde de cuatro módulos y geometría alineada a puntos del perfil. Sin QR fiscal ni CUFE. No se cargan recursos remotos al generar el recibo.

Layout por perfil de papel/ancho útil/DPI; el controlador debe usar escala 100% y márgenes calibrados. Texto térmico reforzado y QR sin suavizado. El perfil Jaltech es una referencia, no un requisito. Otros anchos/modelos pueden añadirse al archivo JSON sin modificar el checkout.

Vista previa e impresión no crean ventas. El navegador solicita un diálogo y no certifica papel impreso. Contador y auditoría productiva de reimpresiones se implementarán con documentos reales en una fase posterior; la demo conserva solamente su snapshot.
