# ADR-001 · Extensión Frappe, demo separada y capacidades de impresión

Estado: adoptada para el scaffold; validación de Bench pendiente. Fecha: 18/10/2026.

- App original `open_multi_pos`, GPL-3.0-only; dependencias upstream fijadas por SHA, sin forks nuevos.
- Candidato Frappe 16.52.0, ERPNext 16.51.1, X POS 2.12.0 en version-16. Compatibilidad declarada coherente con Python 3.14 y Node >=24, aún sin instalación combinada probada.
- Preferir web y controlador del sistema. La impresora se describe por ancho de papel, ancho útil, puntos, corte y capacidades; nunca se selecciona por una marca codificada en el checkout.
- Jaltech JAL 58M: perfil de referencia 57 mm / 384 puntos / 203 DPI / corte manual según fabricante; sin validación física. Perfil genérico 58 y 80 mm para otras impresoras; sus valores se calibran por modelo.
- No enviar corte, abrir cajón ni QR nativo si no está expresamente verificado. No incluir puente de impresión en este incremento.
- Demo independiente para revisión de flujo cuando no existe Bench. Su backend simulado no procesa ventas reales ni conecta a ERPNext.
- Fiscal desactivado, offline comercial pendiente. No guardar contraseñas en el demo.

Consecuencia: se puede revisar y probar el diseño ya, manteniendo como puerta obligatoria la integración real antes de operar. Un prototipo que imita permisos no prueba seguridad de Frappe/X POS.
