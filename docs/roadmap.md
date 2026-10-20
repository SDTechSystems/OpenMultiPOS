# Plan de desarrollo para la operación administrativa

La prioridad es gestionar dos negocios desde cuentas personales de administración, con Windows para el navegador, la impresora y el lector existentes. El backend continúa en WSL. Idioma inicial: español latinoamericano; formato es-CO, COP y America/Bogota. Los valores se configuran en Ajustes.

La identidad, los contactos, los NIT, los productos y las cuentas reales se configuran en la instalación privada. El repositorio y las capturas usan datos ficticios. La relación entre negocios y entidades legales se elige durante la instalación; no se presupone un NIT compartido.

| Prioridad | Entrega | Seguimiento y criterio |
| --- | --- | --- |
| P0 | Espacio administrativo `/omp`, menú con iconos, buscador y selector de negocio | [F20 · #8](https://github.com/JSX2011/OpenMultiPOS/issues/8). Acciones conectadas a documentos reales y contexto visible. |
| P0 | Perfil comercial y datos de recibo por negocio | [F21 · #9](https://github.com/JSX2011/OpenMultiPOS/issues/9). Nombre, razón social, NIT, teléfono, correo, dirección, mensaje y QR editables; visibilidad independiente e historial inmutable. |
| P0 | Primera cuenta humana y administración del equipo | [F22 · #10](https://github.com/JSX2011/OpenMultiPOS/issues/10). Alta desde sesión de instalación, sin registro administrativo público; perfiles posteriores solo por un administrador. |
| P0 | Productos, precios, almacenes y lector instalado | [F23 · #11](https://github.com/JSX2011/OpenMultiPOS/issues/11). Propietario visible, entrada nativa y recuperación sin duplicados. |
| P0 | Cesta de ambos negocios y recibo interno conjunto | [F24 · #12](https://github.com/JSX2011/OpenMultiPOS/issues/12). Una transacción; facturas/stock/cuentas separados; fallo de una parte revierte ambas. |
| P0 | Papel eficiente con el equipo Windows existente | [F25 · #13](https://github.com/JSX2011/OpenMultiPOS/issues/13). Página 48 mm, contenido 44 mm, altura medida y margen superior 0,5 mm; navegador con Márgenes Mínimo y sin encabezados/pies. |
| P0 | Compras, proveedores, clientes, pedidos y finanzas | [F26 · #14](https://github.com/JSX2011/OpenMultiPOS/issues/14). Formularios e informes nativos accesibles en el menú; empresa, permisos y documentos conservados. |
| P0 | Manual, capturas, guías y ayuda por opción | [F27 · #15](https://github.com/JSX2011/OpenMultiPOS/issues/15). Diez secciones documentadas, tutoriales opcionales y capturas exclusivamente ficticias. |
| P0 | SKU automático por negocio y datos del producto | [F28 · #16](https://github.com/JSX2011/OpenMultiPOS/issues/16). Prefijo editable, nombre normalizado y consecutivo; no modifica códigos existentes y recupera el alta con la misma clave. |
| P0 siguiente | Recuperación operativa y revisión antes de datos reales | [#7](https://github.com/JSX2011/OpenMultiPOS/issues/7). Reinicio, copia, restauración aislada y conciliación de ventas/stock/contabilidad; revisar APIs upstream restantes. |
| P1 | Devoluciones guiadas, importaciones y flujos de costos/garantías | [#7](https://github.com/JSX2011/OpenMultiPOS/issues/7). Usar documentos nativos y probar el recorrido completo antes de añadir accesos rápidos. |
| P1 | Ferias y operación sin conexión | [#6](https://github.com/JSX2011/OpenMultiPOS/issues/6). Fuera del checkout actual: reserva, cola, conflictos y conciliación requieren su propia implementación y pruebas. |
| P3 | Integración fiscal separada | DIAN desactivada. Requiere un encargo independiente y validación vigente. |

## Entrega actual

La rama `codex/business-workspace` parte de `main` e incorpora la base validada de caja. Añade el espacio administrativo y los requisitos F20-F28. [El informe de auditoría](audit-report.md) registra pruebas y límites; [el manual](manual.md) explica la operación. El acceso de cajero existente `/omp_pos` sigue disponible.

Los administradores pueden mantener una apertura personal por negocio. La extensión conserva las comprobaciones nativas de perfil, empresa y cuentas; el cierre consulta facturas por usuario y perfil. Una cesta conjunta solo admite la misma moneda y mantiene una factura por negocio, incluso cuando comparten entidad legal.

La moneda de Ajustes se propone para entidades nuevas. No se transforma la moneda contable de una empresa con movimientos ni se reescriben recibos. Idioma y formato se pueden cambiar sin modificar importes; el manual se mantiene en español.

## Alcance de equipos

El propietario confirmó que la impresora imprime normalmente. Las fotografías solo sirvieron de referencia privada para el uso de papel. Se conserva el preset que funciona; no se exige otro ensayo físico, otra impresora, otro lector ni una matriz universal de fabricantes. Los perfiles genéricos históricos y sus pruebas permanecen como regresión de la base, sin ampliar el alcance de esta personalización. El helper RAW es un diagnóstico histórico opcional, no un paso obligatorio de la operación.

El navegador no puede imponer silenciosamente la cola, los márgenes o los encabezados del controlador. La aplicación prepara un documento corto; un formulario fijo de 210 mm puede conservar esa longitud en el controlador. Se utiliza tamaño adaptable si el equipo lo ofrece.

## Base conservada

Nueve pruebas Bench, 19 HTTP de seguridad, 20 HTTP de caja y el recorrido previo de Chrome Windows cubren la base. Las 14 rutas originales de factura X POS continúan bloqueadas. [#2](https://github.com/JSX2011/OpenMultiPOS/issues/2) conserva el seguimiento maestro; [#3](https://github.com/JSX2011/OpenMultiPOS/issues/3), [#4](https://github.com/JSX2011/OpenMultiPOS/issues/4) y [#5](https://github.com/JSX2011/OpenMultiPOS/issues/5) mantienen la evidencia técnica anterior. No se fusiona a `main` automáticamente.
