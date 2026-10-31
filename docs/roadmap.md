# Plan de desarrollo para la operación administrativa

La prioridad es gestionar dos negocios desde cuentas personales de administración, con Windows para el navegador, la impresora y el lector existentes. El backend continúa en WSL. Idioma inicial: español latinoamericano; formato es-CO, COP y America/Bogota. Los valores se configuran en Ajustes.

La identidad, los contactos, los NIT, los productos y las cuentas reales se configuran en la instalación privada. El repositorio y las capturas usan datos ficticios. La relación entre negocios y entidades legales se elige durante la instalación; no se presupone un NIT compartido.

| Prioridad | Entrega | Seguimiento y criterio |
| --- | --- | --- |
| P0 | Espacio administrativo `/omp`, menú con iconos, buscador y selector de negocio | [F20 · #8](https://github.com/SDTechSystems/OpenMultiPOS/issues/8). Acciones conectadas a documentos reales y contexto visible. |
| P0 | Perfil comercial y datos de recibo por negocio | [F21 · #9](https://github.com/SDTechSystems/OpenMultiPOS/issues/9). Nombre, razón social, NIT, teléfono, correo, dirección, mensaje y QR editables; visibilidad independiente e historial inmutable. |
| P0 | Primera cuenta humana y administración del equipo | [F22 · #10](https://github.com/SDTechSystems/OpenMultiPOS/issues/10). Alta desde sesión de instalación, sin registro administrativo público; perfiles posteriores solo por un administrador. |
| P0 | Productos, precios, almacenes y lector instalado | [F23 · #11](https://github.com/SDTechSystems/OpenMultiPOS/issues/11). Propietario visible, entrada nativa y recuperación sin duplicados. |
| P0 | Cesta de ambos negocios y recibo interno conjunto | [F24 · #12](https://github.com/SDTechSystems/OpenMultiPOS/issues/12). Una transacción; facturas/stock/cuentas separados; fallo de una parte revierte ambas. |
| P0 | Papel eficiente con el equipo Windows existente | [F25 · #13](https://github.com/SDTechSystems/OpenMultiPOS/issues/13). Página 48 mm, contenido 44 mm, altura medida y margen superior 0,5 mm; navegador con Márgenes Mínimo y sin encabezados/pies. |
| P0 | Compras, proveedores, clientes, pedidos y finanzas | [F26 · #14](https://github.com/SDTechSystems/OpenMultiPOS/issues/14). Formularios e informes nativos accesibles en el menú; empresa, permisos y documentos conservados. |
| P0 | Manual, capturas, guías y ayuda por opción | [F27 · #15](https://github.com/SDTechSystems/OpenMultiPOS/issues/15). Doce secciones documentadas, tutoriales opcionales y capturas exclusivamente ficticias. |
| P0 | SKU automático por negocio y datos del producto | [F28 · #16](https://github.com/SDTechSystems/OpenMultiPOS/issues/16). Prefijo editable, nombre normalizado y consecutivo; no modifica códigos existentes y recupera el alta con la misma clave. |
| P0 implementado | Recuperación operativa y cierre de APIs anteriores | [#7](https://github.com/SDTechSystems/OpenMultiPOS/issues/7). Reinicio real de servicios, sesiones/intentos; copia privada diaria y restauración aislada de 18 tablas/archivos/secretos con conciliación; gate HTTP de X POS. Fusionado en `main` mediante #17, sin reemplazar el sitio operativo. |
| P1 integrado | Reclamaciones de garantía | [#21](https://github.com/SDTechSystems/OpenMultiPOS/issues/21). Vinculadas a venta/artículo, con estado, fechas y notas; HTTP y navegador reales aprobados localmente. Integrado en `main` con la rama de entrega. |
| P1 integrado | Costos de compra y márgenes | [#22](https://github.com/SDTechSystems/OpenMultiPOS/issues/22). LCV integrado mediante #42. La rama de entrega añade colas de recálculo y Gross Profit nativo; validación registrada en auditoría. |
| P1 integrado | Vista previa del recibo en Impresión de ERPNext | [#18](https://github.com/SDTechSystems/OpenMultiPOS/issues/18). Integrado mediante #35. Selección autorizada, instantánea histórica y vista compacta sin cobrar ni marcar como impreso. |
| P1 integrado | Devoluciones guiadas por negocio | [#19](https://github.com/SDTechSystems/OpenMultiPOS/issues/19). Notas crédito parciales/totales vinculadas, stock y reembolsos nativos, recuperación sin duplicados y comprobante histórico. Integrado mediante #36. |
| P1 | Ferias y operación sin conexión | [#6](https://github.com/SDTechSystems/OpenMultiPOS/issues/6). Fuera del checkout actual: reserva, cola, conflictos y conciliación requieren su propia implementación y pruebas. |
| Entrega | Edición portable e instalador Windows compartibles | [#37](https://github.com/SDTechSystems/OpenMultiPOS/issues/37). Paquetes limpios, componentes gestionados, actualización/recuperación y pruebas en Windows sin checkout de desarrollo. |
| Entrega | Primera configuración guiada y reanudable | [#38](https://github.com/SDTechSystems/OpenMultiPOS/issues/38). Acceso inicial, negocios, preferencias, inventario, equipos, recibo y respaldo. Ver [criterios de entrega](release-onboarding.md). |
| P3 | Integración fiscal separada | DIAN desactivada. Requiere un encargo independiente y validación vigente. |

## Entrega actual

El espacio administrativo y los requisitos F20-F28 están integrados en `main` mediante #17. La vista previa #18 está integrada mediante #35. Las devoluciones #19 están integradas mediante #36. Importar inventario #20 está integrado mediante #40: preparación CSV, errores por fila, revisión y aplicación atómica de catálogo y entradas nativas. Las restricciones adicionales para cajeros de #3 están integradas mediante #41; la revisión de otras APIs sigue abierta. La primera entrega de costos de compra está integrada mediante #42. La conciliación de recálculos y los márgenes están implementados en la rama de entrega, pendientes de integración. [El informe de auditoría](audit-report.md) registra pruebas y límites; [el manual](manual.md) explica la operación. El acceso de cajero existente `/omp_pos` sigue disponible.

Los administradores pueden mantener una apertura personal por negocio. La extensión conserva las comprobaciones nativas de perfil, empresa y cuentas; el cierre consulta facturas por usuario y perfil. Una cesta conjunta solo admite la misma moneda y mantiene una factura por negocio, incluso cuando comparten entidad legal.

La moneda de Ajustes se propone para entidades nuevas. No se transforma la moneda contable de una empresa con movimientos ni se reescriben recibos. Idioma y formato se pueden cambiar sin modificar importes; el manual se mantiene en español.

## Alcance de equipos

El propietario confirmó que la impresora imprime normalmente. Las fotografías solo sirvieron de referencia privada para el uso de papel. Se conserva el preset que funciona; no se exige otro ensayo físico, otra impresora, otro lector ni una matriz universal de fabricantes. Los perfiles genéricos históricos y sus pruebas permanecen como regresión de la base, sin ampliar el alcance de esta personalización. El helper RAW es un diagnóstico histórico opcional, no un paso obligatorio de la operación.

El navegador no puede imponer silenciosamente la cola, los márgenes o los encabezados del controlador. La aplicación prepara un documento corto; un formulario fijo de 210 mm puede conservar esa longitud en el controlador. Se utiliza tamaño adaptable si el equipo lo ofrece.

## Base conservada

Nueve pruebas Bench, 21 HTTP de seguridad, 20 HTTP de caja y el recorrido previo de Chrome Windows cubren la base. Las 14 rutas originales de factura X POS continúan bloqueadas. [#2](https://github.com/SDTechSystems/OpenMultiPOS/issues/2) conserva el seguimiento maestro; [#3](https://github.com/SDTechSystems/OpenMultiPOS/issues/3), [#4](https://github.com/SDTechSystems/OpenMultiPOS/issues/4) y [#5](https://github.com/SDTechSystems/OpenMultiPOS/issues/5) mantienen la evidencia técnica anterior. No se fusiona a `main` automáticamente.

## Recuperación y seguridad de la entrega

Ver [respaldo y restauración](recovery.md) y [revisión de APIs](upstream-api-review.md). La interfaz de Ajustes muestra fechas de copia/ensayo; el manual conserva los procedimientos del operador. Las copias son privadas y locales: el destino externo se configura por separado. El cliente X POS anterior no se usa para operar.

## Próximas entregas

- #21: reclamaciones de garantía implementadas en PR #43, con HTTP y navegador reales aprobados localmente. Completar regresiones remotas antes de integrar. No incluye servicios pagados ni periodos o plazos automáticos.
- #22: completar la validación de la rama de entrega e integrar la consulta de recálculos y márgenes nativos. Costos de compra y recuperación ya están integrados mediante #42.
- #37 y #38: versiones Windows portátil e instalable y configuración inicial guiada, reanudable y en español. Se construirán cuando la base funcional esté lista, con instalaciones limpias sin datos, claves ni respaldos privados. Los requisitos y criterios de aceptación se registran en #39 y [release-onboarding.md](release-onboarding.md); los paquetes y el asistente integral siguen sin implementar.
- #6: operación sin conexión, con su propia conciliación.

### Primera entrega de #22: distribución de costos

Sección guiada Costos de compra con LCV nativo, moneda original ligada a la cuenta, tasa explícita, distribución y vista previa por artículo, estimación en borrador y recuperación por clave única. PR #42 incorpora la corrección del bloqueo de recuperación: abandono persistente en servidor, recuperación de su respuesta perdida y reconocimiento del comprobante cancelado aunque su compra también se cancele. [Guía y límites](landed-costs.md). Esa primera entrega cubrió parcialmente #22. La rama de entrega añade consulta de colas de valoración/contabilidad y Gross Profit nativo por almacén. Se ocultan importes durante recálculos abiertos o ante informes de instantánea; la integración completa se decide con la evidencia de auditoría.

## Distribución final y primera ejecución

Al completar el alcance acordado, entregar edición portable y edición instalable para compartir, con configuración inicial guiada. Los artefactos se generan limpios, sin datos ni credenciales del propietario, y se prueban en Windows sin el entorno de desarrollo. El asistente debe reanudar pasos, explicar errores y conducir a una operación preparada. [Diseño, etapas y criterios verificables](release-onboarding.md).
