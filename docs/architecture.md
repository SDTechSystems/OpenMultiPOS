# Arquitectura

```mermaid
flowchart LR
    Admin[Administración /omp] --> O
    POS[Caja web propia /omp_pos] --> O
    X[X POS: rutas originales de factura bloqueadas] --> F[Frappe / ERPNext v16]
    O[App open_multi_pos] --> F
    O --> B[Marca → Company / Warehouse / POS Profile]
    O --> N[Servicio autorizado → Sales Invoice / stock / GL]
    N --> J[Clave única + snapshot persistente]
    J --> R[Instantánea de recibo interno]
    R --> P[PrinterAdapter + perfil de capacidades]
    P --> V[Vista previa / navegador + controlador]
    O --> D[Proveedor fiscal desactivado]
    Demo[Demo local ficticia] --> Sim[Simulador separado, sin ERPNext]
```

ERPNext conserva catálogo, precios, impuestos, documentos, stock y contabilidad. La extensión añade marca, terminales, un servicio autorizado de caja y journals privados de idempotencia/snapshot. No copia ni modifica core. El backend en línea usa Sales Invoice con stock/GL inmediatos y aperturas/cierres nativos. La pantalla autenticada `/omp_pos` usa el contrato de [native-checkout.md](native-checkout.md); no usa el ledger de demo ni creación de factura X POS. [Uso y recuperación](cashier-ui.md).

Desarrollo local validado: backend y herramientas en Ubuntu WSL; navegador, controlador de impresión y lector en Windows. Chrome Windows alcanza el servicio web WSL en loopback y ejecutó el recorrido de venta/recuperación/cierre con dos cajeros. La conexión de varios computadores requiere un servidor accesible con autenticación/TLS; no se habilita exponiendo el sitio de ensayo. Ver [local-services.md](local-services.md).

Una marca no es una entidad legal. Su configuración referencia Company, Warehouse y POS Profile; se valida que pertenezcan a la misma Company y que el almacén coincida con el perfil. Acceso por lista explícita de usuarios más permisos nativos. La selección del cliente nunca concede acceso.

Demo: servidor loopback y SQLite con datos ficticios, dos usuarios de simulación elegibles y tres perfiles de impresora. La selección de usuario es un control de demostración, no un login. Ningún impuesto/ledger simulado debe reutilizarse como motor productivo.

Impresión: el recibo es una instantánea de marca y líneas al completar la venta. Cambiar impresora solo cambia el layout; no recrea la venta. El navegador no certifica que salió papel. Estado del trabajo: vista previa, diálogo solicitado o error; no marcar impreso sin confirmación física.

Ver [ADR-001](decisions/ADR-001-base.md), [upstream.md](upstream.md) y [offline-sync.md](offline-sync.md).

El navegador persiste solo el payload del intento (terminal, UUID, quote y medios/importes) por sitio/usuario, antes del POST. Web Locks serializa pestañas del mismo origen/perfil; otro navegador/equipo no comparte ese bloqueo. No persiste catálogo, cliente ni snapshot. El tombstone servidor de `abandon_checkout` comparte el mutex del checkout y bloquea claves/cotizaciones liberadas, incluso ante una solicitud tardía. No concilia pagos externos ni implementa offline.


## Espacio administrativo y cesta conjunta

`workspace.py` exige sesión administrativa antes de leer o escribir. Crea documentos nativos para negocio, catálogo, precio, existencias y usuarios; no usa `ignore_permissions`. La relación negocio/Company se elige al crear el negocio. Los administradores tienen roles nativos de gestión; un cajero no recibe esos roles ni acceso al espacio administrativo.

`batch.py` autoriza las terminales, toma bloqueos de perfil en orden común y agrupa hasta dos servicios de checkout en la misma transacción de Frappe. Si falla un hijo, se revierten las dos facturas y sus efectos. El journal privado usa clave usuario/UUID y hash del payload. Estado, reintento y resolución no generan otra clave. Una marca de abandono bloquea solicitudes tardías. La instantánea conjunta conserva los snapshots nativos por negocio y sus opciones de contacto; la vista previa no vuelve a cotizar ni cobrar.

Las entradas de inventario usan una clave única en Stock Entry, hash de payload y una marca privada para bloquear intentos abandonados. Web Locks coordina pestañas del mismo navegador. Un bloqueo o interbloqueo nativo puede responder 409: el cliente conserva el intento y lo recupera con la misma clave.

Una extensión de clase Frappe permite una apertura por usuario/perfil para administradores de negocios visibles en `/omp`. No modifica core; mantiene validaciones nativas de empresa, cuentas y estado. Los cajeros y perfiles ajenos al espacio conservan la regla original. El cierre nativo filtra facturas por propietario y perfil.

Compras, finanzas, clientes y entidad legal se muestran en formularios/informes nativos dentro del espacio, con idioma y filtro de empresa. El filtro es contexto de trabajo, no un permiso. Los administradores conservan acceso administrativo al sitio; los permisos de cajero se verifican en servidor.

## Devoluciones guiadas

`returns.py` exige administración, terminal personal y acceso actual al negocio y a la factura original del journal de caja. Usa el mapper nativo de nota crédito y conserva precios/impuestos originales; no copia el motor contable. Bloquea perfil, factura original e intento, consulta devoluciones enviadas con lectura actual y valida cantidades e importe acumulado. La huella de cálculo detecta cambios antes de registrar. Cada nota conserva su empresa, perfil, almacén y factura original; las dos facturas de una cesta se devuelven por separado.

El journal privado `OMP Return Request`, identificado por usuario/UUID, guarda payload, estado, nota y comprobante en la misma transacción que stock, GL y pagos negativos nativos. Un abandono bloquea envíos tardíos; recuperación/reintento no crea otra nota. La revisión de apertura avanza al reembolsar para que el cierre no use una vista anterior. La copia/restauración incluye este journal como tabla número 19.

El navegador conserva el payload del intento antes de enviar, por sitio/usuario, y coordina pestañas con Web Locks. No conserva el comprobante en almacenamiento local. La interfaz no ejecuta transferencias ni confirma entrega de efectivo. Series/lotes, ajustes globales, fracciones y diferencias de redondeo requieren el formulario nativo; el servicio falla antes de registrar si no puede conciliar cantidades/importes.

## Importación guiada de catálogo y existencias

`imports.py` autoriza al administrador y su negocio en cada llamada POST. `import_contract.py` valida CSV UTF-8 con límites de filas/tamaño, campos tipados y rechazo de fórmulas. La preparación conserva filas normalizadas y plan en `OMP Import Request`, privado; no escribe catálogo ni ledger. El navegador persiste solo negocio, usuario/origen, UUID, fase, hash y confirmación de repetición, sin CSV ni catálogo.

Perfil, negocio, intento, productos, precios y existencias se leen bajo bloqueos. El hash del plan incluye sus revisiones; aplicar vuelve a calcularlo y exige revisar cualquier cambio. Los índices de negocio/nombre y negocio/contenido/estado se crean durante instalación/migración. Se bloquean SKU y códigos repetidos, productos ajenos y configuraciones nativas no soportadas. Las lecturas de precios y movimientos previos usan consultas actuales después de esperar bloqueos.

Crear usa el servicio existente de SKU; actualizar conserva el código y agrega códigos de barras sin sustituirlos. Las cantidades son entradas adicionales, consolidadas en una Stock Entry de Material Receipt. Item, Item Price, Stock Entry enviada, SLE, GL y resultado del journal comparten transacción y permisos nativos. Un fallo revierte todo. No se modifica core ni se usa ignore_permissions. Los reintentos de un UUID devuelven el resultado original; abandonar deja una marca que bloquea solicitudes tardías. Repetir contenido con otra clave requiere confirmación explícita; no identifica entregas físicas por sí solo.

La recuperación vuelve a autorizar productos y documento nativo. Un movimiento anulado no se recrea por reintento. El respaldo completo incluye filas normalizadas y resultados privados; la conciliación añade Item Barcode y OMP Import Request, para 21 tablas.

## Distribución guiada de costos de compra

`landed_costs.py` autoriza administración y negocio en cada POST; conserva permisos nativos al leer compras/cuentas y crear, guardar o enviar un Landed Cost Voucher. Bloquea perfil, negocio, compras y artículos; valida pertenencia de todas las filas al negocio/almacén. Las tasas explícitas y la moneda de la cuenta se validan antes del cálculo nativo. El contrato de entrada usa Decimal y cadenas decimales; ERPNext conserva su implementación de distribución, redondeo y valoración.

Cinco campos de extensión del LCV conservan clave única, hash de contenido/acción, negocio, actor y vista previa final. La creación del documento, su envío y los efectos nativos comparten transacción. La recuperación reautoriza documentos y no recrea comprobantes cancelados. Los borradores se ajustan en ERPNext y deben revisarse nuevamente antes de enviarse desde OMP. Un hook before_submit exige la capacidad privada del servicio para los LCV con clave OMP; evita enviar desde Desk con una instantánea de estimación obsoleta y conserva el flujo nativo de otros LCV. La vista incluye revisión del borrador, revisiones de compras y cargos previos para detectar cálculos obsoletos. Ver [operación y límites](landed-costs.md).

`OMP Landed Cost Tombstone` conserva únicamente usuario y negocio, bajo la misma clave y los mismos bloqueos de perfil/negocio del envío. Abandonar recupera un LCV existente o bloquea futuras solicitudes con esa clave; no elimina ni cancela comprobantes. El navegador conserva el intento hasta observar un resultado del servidor, incluso si pierde la respuesta de abandono. El comprobante cancelado se puede reconocer aunque después se cancele su compra. La restauración compara las cinco tablas nativas de LCV y la marca de abandono, para 27 tablas.

## Garantías vinculadas a una venta

`warranties.py` exige administración y acceso actual al negocio y a la venta de caja. Crea un Warranty Claim nativo con empresa, cliente y artículo de la venta; campos de extensión conservan negocio, factura, línea y clave única. Hooks protegen esos vínculos y evitan eliminar el registro guiado. No modifica core ni genera pagos, notas crédito o stock.

Perfil, negocio, intento y documento se leen bajo bloqueos. OMP Warranty Request conserva actor, negocio, huella, estado y reclamación dentro de la misma transacción del alta. Consultar/reintentar recupera el documento; abandonar recupera el alta existente o bloquea solicitudes tardías. El navegador mantiene el payload privado hasta confirmar el resultado. Ediciones usan la revisión nativa del documento y rechazan una versión obsoleta; repetir el resultado ya guardado no vuelve a editarlo. La conciliación de restauración incluye documento y journal: 29 tablas.

## Consulta de valoración y margen

`valuation.review` autoriza administración y acceso al negocio, valida un intervalo de hasta 366 días y conserva los roles/permisos nativos de Gross Profit y de las tareas de recálculo. Consulta tareas enviadas abiertas de Repost Item Valuation y Repost Accounting Ledger para la empresa; incluye las tareas contables sin empresa como precaución. Una tarea fallida o parcial oculta los importes. Los recálculos contables separados de stock también mantienen ese bloqueo.

Con las colas despejadas, usa el ejecutor nativo del informe con empresa y almacén derivados del contexto autorizado. El filtro de almacén incluye descendientes nativos. No usa informes preparados y rechaza la configuración de instantánea. Importes y totales proceden de Gross Profit; la extensión no calcula costos ni vuelve a escribir SLE/GL. Conserva decimales serializados como texto y formato monetario nativo para presentación. El resultado representa el momento observado, sin actualización automática ni promesa de inmovilidad frente a otros usuarios. Cambios de contexto, fechas y acciones de costos limpian la consulta anterior. La comparación de restauración se amplía a 32 tablas con los registros de recálculo.
