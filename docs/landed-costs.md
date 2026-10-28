# Costos de compra

En `/omp`, selecciona el negocio y abre **Costos de compra**. Registra primero las compras en ERPNext. La herramienta crea un **Landed Cost Voucher** nativo; no crea cuentas, documentos fiscales ni un ledger propio. Requiere administración del espacio y permisos nativos de Stock Manager.

1. Selecciona hasta diez recepciones enviadas o facturas enviadas con Actualizar existencias. Todas las filas deben pertenecer al negocio y a su almacén. No selecciones documentos que representen dos veces la misma mercancía.
2. Elige distribución por importe base o cantidad. Usa cantidad solo para unidades comparables.
3. Agrega hasta veinte costos. La cuenta debe estar activa, pertenecer a la empresa y ser de tipo **Expenses Included In Valuation** (gastos incluidos en valoración). La moneda original es la moneda de esa cuenta, conforme al LCV nativo. Si necesitas otra moneda, configura su cuenta nativa en ERPNext. Escribe el importe original y la tasa explícita: unidades de moneda contable por unidad original. La tasa de la misma moneda debe ser 1.
4. Calcula la vista previa y revisa los costos convertidos, la distribución por artículo y sus costos unitarios antes/después, en moneda contable. Confirma la revisión.
5. **Guardar estimación en borrador** conserva un LCV sin enviar: no cambia la valoración. **Enviar distribución definitiva** envía el LCV y deja a ERPNext registrar sus efectos.

Para ajustar una estimación, abre el comprobante en ERPNext, cambia los costos y guarda el borrador. Regresa y pulsa **Consultar estado**, revisa la vista actual y confirma antes de **Enviar estimación revisada**. El servicio vuelve a obtener las líneas de las compras; no acepta una tabla de artículos modificada manualmente. El envío de un borrador creado por OMP se hace desde esta sección; el botón Enviar nativo se rechaza para conservar la vista previa final revisada. Los LCV creados directamente en ERPNext mantienen su flujo nativo. Documentos con facturas de servicios vinculadas o distribución manual se gestionan íntegramente en ERPNext.

## Respuestas perdidas y cambios concurrentes

El navegador conserva negocio, usuario/origen, contenido e identificador antes de enviar. **Consultar estado** recupera el comprobante. **Reintentar la misma operación** usa la misma clave; no crea un segundo LCV. Conserva el almacenamiento local y el mismo usuario hasta resolver el intento. La clave única en base de datos pertenece al usuario y al intento; también se comprueba el contenido y la acción elegida.

Un bloqueo nativo puede responder 409 y revertir la solicitud. Consulta el estado y reintenta. Si cambió el costo o la recepción, usa **Actualizar vista previa del mismo intento**, revisa y confirma el nuevo cálculo antes de reintentar. No cambies de clave para resolver una respuesta incierta. Un comprobante cancelado no se vuelve a crear al reintentar; consulta el estado para confirmar la cancelación y liberar el intento antes de preparar otra distribución. La herramienta no detecta si dos claves nuevas representan el mismo flete físico.

Si la compra fue cancelada, una cuenta dejó de ser válida o no puedes corregir el intento, pulsa **Abandonar intento pendiente**. El servidor espera cualquier envío en curso: si ya existe un comprobante, lo recupera; si no existe, guarda una marca privada que bloquea solicitudes tardías con esa clave. No borra ni cancela comprobantes nativos. Solo después de confirmar el abandono puedes pulsar **Preparar otra distribución**. Si se pierde la respuesta al abandonar, recarga o consulta el estado con la misma clave; no borres el almacenamiento del navegador para desbloquear la sección.

## Alcance de la valoración

El costo previo es la tasa de valoración nativa de la fila de recepción, incluidos sus impuestos de valoración y costos LCV anteriores. El costo posterior suma `distribución nueva / cantidad` a esa tasa. No es el costo promedio actual del almacén ni un margen. ERPNext distribuye y redondea los cargos con sus reglas nativas. No se escriben directamente SLE, GL ni movimientos históricos desde la extensión. El envío nativo recalcula la recepción y puede programar recálculos de movimientos posteriores; esta pantalla no certifica que hayan terminado.

La distribución guiada excluye activos, series/lotes, cantidades negativas, rechazos y conversiones de unidad. Compras con filas de varios negocios requieren el flujo nativo revisado por un administrador. El listado ofrece documentos enteramente pertenecientes al negocio entre los cincuenta más recientes de cada tipo; no constituye una búsqueda histórica completa.

## Recálculos y margen bruto

Abre **Revisar recálculos y margen bruto**, selecciona un intervalo de hasta un año y pulsa **Consultar recálculos y margen**. El valor inicial es el mes actual. La consulta exige acceso al negocio y los permisos nativos de Gross Profit y de las tareas de recálculo. No envía costos ni ejecuta recálculos.

Si hay tareas enviadas abiertas de valoración o contabilidad en la empresa, la tabla muestra sus estados y enlaces a ERPNext. Incluye trabajos de otros almacenes de esa empresa y trabajos contables sin empresa definida. Se muestran hasta cincuenta de cada tipo, con aviso si hay más. Un fallo o un estado parcial conserva los importes ocultos. Revisa el error y el procedimiento de reintento en el documento nativo; no vuelvas a registrar el flete. Un recálculo de stock completado puede dejar otro recálculo contable pendiente.

Con las colas despejadas, se ejecuta Gross Profit nativo sin usar un informe preparado. Si está configurado como informe de instantánea, se ocultan los importes hasta revisar esa configuración. Las filas muestran ventas netas, costo de mercancía, margen bruto y porcentaje por artículo, con el total calculado por ERPNext, en moneda contable y formato monetario nativo. El almacén activo incluye sus subalmacenes. La vista representa ese almacén; no filtra por POS Profile ni equivale a utilidad neta, saldo de caja o conciliación bancaria. Dos negocios que compartan almacén comparten el alcance del informe.

La fecha y zona horaria indican el momento de la consulta. No se actualiza automáticamente. Consulta de nuevo después de cambios realizados desde otra pantalla o computador. Cambiar fechas o negocio, enviar una distribución o recuperar su estado limpia la consulta anterior. Abrir informe nativo conserva empresa, almacén y fechas y permite revisar su detalle con permisos nativos. Un filtro de contexto no restringe el acceso administrativo al sitio.

El respaldo completo de Frappe incluye los LCV, sus campos OMP, marcas de abandono y tareas nativas de recálculo. La comparación de restauración incluye las cinco tablas de LCV y tres tablas de recálculo, para 32 tablas junto con los journals de garantías. Los resultados del ensayo sobre este cambio se registran por separado en el informe de auditoría.

## Validación

`scripts/test-landed-costs-http.py --bench <ruta>` usa exclusivamente un sitio loopback desechable con `allow_tests`, documentos ficticios y permisos reales. Comprueba doce escenarios HTTP: valoración/GL y recuperación, borrador editado y revisión, concurrencia y clave vinculada al payload, aislamiento/monedas, vista obsoleta/cancelación, factura con stock, dos recepciones con costo USD y tasa explícita, rechazo de cajero/rollback nativo, impuestos previos de valoración, abandono tras rechazo, carrera envío/abandono y cancelación de compra después del LCV. El navegador comprueba también la pérdida de la respuesta de abandono y su recuperación tras recargar. El tutorial está en la ayuda de `/omp`. Los contratos puros se prueban aparte; no sustituyen ERPNext.
