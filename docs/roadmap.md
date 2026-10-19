# Plan de ejecución

| Fase | Entrega | Criterios de salida |
| --- | --- | --- |
| 0 · Descubrimiento | Fuentes fijadas, licencias, gaps, riesgos y ADR | Evidencia por ruta/commit; distinguir código revisado de integración probada. |
| 1 · Base | App Frappe instalable, perfiles/permisos y terminal de prueba | Bench v16: dos marcas, rechazo de acceso cruzado y venta nativa con stock exacto. Demo local para revisión temprana. |
| 2 · Hardware y recibos | Perfiles 58/80 mm, branding, QR y lector | Vista previa y pruebas físicas por modelo/driver/firmware; reimpresión sin otra venta. |
| 3 · Ferias | Traslados, cola offline y conciliación | Cortes de red, dos reintentos, concurrencia y conflictos sin duplicados. |
| 4 · Operación | Pedidos, compras, descuentos, reportes, importaciones y backups | Encargo hasta entrega; restauración aislada y conciliación. |
| 5 · Fiscal | Proyecto de adaptador independiente | Requiere encargo nuevo y verificación técnica/legal vigente. Sin envío DIAN en MVP. |

## Backlog ordenado

1. **P0 / S**: publicar requisitos, fuentes y arquitectura con evidencia.
2. **P0 / M**: estructura app Frappe, perfiles y permisos; demo revisable y CI.
3. **P0 / L**: levantar Bench fijado; pruebas de instalación y acceso directo a API/DocTypes; revisar endpoints X POS antes de uso real.
4. **P0 / L**: conectar checkout nativo; clave idempotente con unicidad en BD, validación de almacén/usuario y concurrencia; pagos mixtos y cierres.
5. **P0 / M**: contexto histórico de recibo y QR, perfiles configurables, navegador/controlador y diagnóstico de impresión.
6. **P0 / M**: ensayos Jaltech y al menos otra impresora; lector HID, foco y terminador.
7. **P1 / L**: offline con stock reservado, conflictos y pruebas de reconexión multi-terminal.
8. **P1 / L**: pedidos, costos, promociones, reportes y restauración.

S/M/L expresan tamaño relativo, no fechas prometidas. Las fases 1 y 2 pueden compartir componentes de demo, pero cada puerta de salida conserva su propia evidencia.

## Próximo incremento después de la base

Preparar entorno Bench reproducible sobre Linux, instalar los SHAs de `upstream.lock.json`, ejecutar pruebas de permisos con dos usuarios y confirmar hooks/contratos X POS. No conectar transacciones reales hasta probar permisos, unicidad y stock. La selección de entidad legal, logotipos y métodos bancarios se configura localmente; no bloquea la base genérica.
