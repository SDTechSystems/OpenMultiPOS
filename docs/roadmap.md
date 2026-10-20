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

Instalación y migración Bench completadas en Ubuntu WSL el 19/10/2026 con los SHAs de `upstream.lock.json`. Nueve pruebas reales validan permisos de marca/perfil con dos usuarios y dos empresas. Las herramientas y el servicio local están documentados en [local-services.md](local-services.md).

Incremento P0 de APIs: acceso cruzado de recibos restringido, contador de impresión protegido y concurrente, detalle con permisos de campos y facturas de cajeros filtradas por marca. Diecinueve pruebas HTTP reales cubren v1/v2 y rutas nativas alternativas. Catorce operaciones de factura X POS permanecen bloqueadas, incluida creación/reintentos; ver [matriz de APIs](xpos-api-security.md). No se modificó core.

Backend de caja nativa completado: 20 pruebas HTTP reales de cotización/checkout, Stock Ledger y GL, impuestos, mixtos/cambio, apertura/cierre, UUID/payload/quote únicos, última unidad entre perfiles y rollback. Journals privados, capacidades por solicitud y snapshot histórico; ver [native-checkout.md](native-checkout.md). Worker local activo para procesar trabajo en segundo plano. Las 14 rutas originales siguen bloqueadas.

Pantalla P0 integrada: `/omp_pos`, sesión/CSRF, terminales autorizadas, cliente de mostrador del perfil, búsqueda/código de barras, teclado US opcional, pagos mixtos y cierre. Chrome Windows pasó recuperación tras respuesta perdida, retry con mismo UUID, dos pestañas, resolución atómica sin venta y fallo de recibo sin otro cobro. Tres perfiles de recibo/PDF, móvil/escritorio y axe probados. Ver [cashier-ui.md](cashier-ui.md).

Próxima tarea P0: ensayar el recibo **nativo** y lector físico con el controlador Windows, registrar avance/corte/legibilidad y fallback por modelo, sin repetir ventas. Después, recuperación operativa (reinicio/backup/restauración) y auditoría restante de upstream antes de datos reales. Devoluciones y offline siguen pendientes.

## Seguimiento en GitHub

- [Plan maestro](https://github.com/JSX2011/OpenMultiPOS/issues/2)
- [Bench y permisos](https://github.com/JSX2011/OpenMultiPOS/issues/3)
- [Checkout y stock nativos](https://github.com/JSX2011/OpenMultiPOS/issues/4)
- [Impresoras y lectores](https://github.com/JSX2011/OpenMultiPOS/issues/5)
- [Offline y ferias](https://github.com/JSX2011/OpenMultiPOS/issues/6)
- [Operación comercial y recuperación](https://github.com/JSX2011/OpenMultiPOS/issues/7)

Implementación inicial en [PR #1](https://github.com/JSX2011/OpenMultiPOS/pull/1).
