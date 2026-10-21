# Revisión y cierre de superficie HTTP de X POS

Alcance P0 de #7, sobre X POS `6392895a955f91b8c7d55574dc01ac5f19459dc3`. [Inventario reproducible](xpos-entrypoints.json): 227 declaraciones `frappe.whitelist` fuera de tests. Incluye `xpos.api`, los módulos históricos `xpos.x_pos.api` y métodos de controladores. El inventario no importa ni ejecuta sus funciones. Los aliases importados y futuros métodos quedan cubiertos por la política de namespace, aunque no sean declaraciones nuevas.

| Grupo | Decisión HTTP |
| --- | --- |
| Contexto de recibo, contador de impresión y detalle de factura | Tres adaptadores propios ya autorizan perfil, documento, campos, usuario y acción. Se rechaza la llamada si el override efectivo deja de ser el adaptador previsto. |
| Facturas originales, devoluciones, repetición y borradores | Bloqueados; el checkout propio mantiene documentos/stock/GL y journals nativos. |
| Clientes, catálogo, sincronización y tablas hijas | Bloqueados. Hay lecturas por `get_all`/SQL y parámetros de contexto del cliente; no se presume que un filtro enviado por el navegador conceda autorización. |
| Turnos, efectivo, pagos, tarjetas regalo, pedidos y cotizaciones | Bloqueados. Pueden crear o modificar documentos y no se conectan al contrato transaccional de OpenMultiPOS. Se usan herramientas nativas autorizadas del espacio. |
| Ofertas, bundles, impuestos, precios, moneda, ajustes, roles y reportes propios de X POS | Bloqueados hasta implementar un contrato específico. Incluso las rutas con controles internos correctos conservan esta política uniforme. |
| APIs históricas y métodos de POS Closing Shift | Bloqueados también por RPC/documento; no basta proteger solo `xpos.api`. |
| Página `/xpos`, alias HTML, service worker y manifest | Bloqueados para impedir abrir el cliente offline anterior como ruta alternativa. Los assets estáticos no se usan para operar. |

`auth_hooks` aplica el control después de autenticar y antes del dispatch, tanto a cajero como a administrador y Guest. Cubre v1, v1 explícito, v2, `cmd` legado, RPC abreviado por DocType, `run_doc_method` con documento en memoria y método de documento guardado. Las clases/documentos nativos conservan sus permisos y las herramientas ERPNext de administración continúan disponibles.

El hook de boot de upstream introduce Singles de ajustes sin comprobar lectura nativa. El último hook de OpenMultiPOS retira esos datos y las claves `xpos_*` de boot para usuarios que no son administradores. No se modifica core. Países, monedas y territorios son catálogos compartidos; los administradores conservan sus capacidades administrativas.

Pruebas HTTP: cada declaración cerrada se solicita en v1/v2 con cajero real; se comprueban además Guest, manager, comandos futuros, POST legado, controladores, aliases de página y worker. Las tres excepciones conservan las regresiones de permisos de documento y acceso cruzado. Un cambio del conteo fijado exige revisar el inventario. La caja nativa y el espacio administrativo se ejecutan nuevamente después del cierre de rutas.

Límite: esto resuelve la exposición HTTP de X POS para esta personalización, no certifica toda Frappe/ERPNext ni dependencias transitivas. Los hooks y llamadas Python internas de aplicaciones instaladas siguen siendo código confiable; no pasan por el gate HTTP. El administrador del sitio tiene permisos amplios por diseño. El acceso multi-equipo por Internet, TLS, offline y fiscal no se habilitan con este incremento.
