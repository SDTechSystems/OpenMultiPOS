# Reclamaciones de garantía

En **Garantías**, selecciona el negocio y consulta el número de la venta original. Elige un artículo, indica la fecha de recepción y describe el motivo. La venta debe estar enviada y pertenecer a la caja del negocio. La fecha no puede ser anterior a la venta ni estar en el futuro.

El servicio crea un **Warranty Claim nativo de ERPNext**, con cliente y empresa de la venta. El vínculo con la venta y su línea es inmutable. El seguimiento muestra Abierta, En revisión, Cerrada o Cancelada, fecha de recepción, cierre y notas. Cerrar usa la fecha nativa de resolución; reabrir retira ese cierre. Si otra persona cambió el registro, vuelve a consultarlo antes de guardar. Un reintento del mismo estado y notas recupera la edición ya guardada.

La lista contiene las 50 reclamaciones modificadas más recientemente del negocio. Para un registro anterior, usa Buscar una reclamación por número. Registrar o actualizar seguimiento no cobra, reembolsa ni mueve inventario. Los reembolsos conservan su flujo de Devoluciones. No incluye órdenes de reparación pagadas, periodos de garantía supuestos ni plazos automáticos. La cobertura se revisa con las condiciones acordadas.

## Recuperar una respuesta perdida

El navegador conserva el contenido y UUID del alta por sitio/usuario antes del envío. Si se interrumpe la conexión, cierra el formulario y usa Consultar intento o Reintentar misma reclamación. Recargar recupera el registro existente sin duplicarlo. No borres el almacenamiento local mientras el intento esté pendiente; puede contener el motivo privado de la reclamación.

Si el alta no puede completarse, Abandonar intento pendiente recupera el resultado existente o registra un abandono privado que bloquea solicitudes tardías con esa clave. Solo después de confirmar el resultado se habilita Nueva reclamación. También se recupera un abandono cuya respuesta se perdió. Dos UUID diferentes representan reclamaciones distintas; revisa el historial antes de crear otra por el mismo problema.

Los permisos administrativos y nativos se comprueban en servidor. Se reautoriza el negocio y la venta al consultar o modificar un registro. Una cancelación posterior de la venta no borra el seguimiento existente, pero impide nuevas reclamaciones sobre esa venta. No se permite eliminar un registro guiado ni cambiar su empresa, cliente o artículo: usa el estado Cancelada para conservar el historial.

El respaldo completo incluye documentos y journals privados. La conciliación de restauración añade Warranty Claim y OMP Warranty Request, para 29 tablas. El código extiende ERPNext mediante campos y hooks soportados; no modifica core.
