# Espacio administrativo

Ruta `/omp`, acceso por sesión con rol System Manager. La cuenta de instalación habilita la primera cuenta humana. Las cuentas administrativas creadas por la interfaz incluyen OMP Administrator y los roles nativos necesarios para catálogo, compras, inventario, ventas y contabilidad. No hay alta pública ni envío automático de correos. Los cajeros usan `/omp_pos` y terminales asignadas.

El sitio debe tener completa la configuración inicial nativa de ERPNext. Si una instalación nueva muestra su asistente, complétalo antes de operar las herramientas contables. El sitio local existente ya está inicializado.

## Configuración inicial

1. Iniciar sesión con la cuenta de instalación y abrir `/omp`.
2. Crear un perfil personal de administrador con correo y contraseña; después iniciar sesión con él.
3. Agregar cada negocio. Elegir entidad existente si corresponde al mismo NIT/contabilidad; crear otra si corresponde a una entidad distinta. No es obligatorio compartir entidad.
4. Completar perfil comercial y opciones de recibo por negocio. Los contactos reales quedan en la base de datos del sitio.
5. Crear la segunda cuenta administrativa y los perfiles adicionales desde Equipo.
6. Crear productos, registrar su recepción o compra, abrir las cajas y operar. Consultar [el manual](manual.md).

## SKU automático

Al crear un producto desde Inventario, el servidor combina el prefijo del negocio, un segmento del nombre sin tildes y un consecutivo de al menos cinco dígitos. El prefijo parte de las iniciales, conserva siglas cortas y se puede editar en Negocios. No cambia códigos existentes. El SKU y el código de barras del empaque son campos distintos.

La serie nativa se bloquea en la base de datos. La creación lleva un UUID y hash de payload, con unicidad en Item. La página conserva el intento y lo recupera tras una respuesta perdida; otra pestaña no crea un producto adicional con ese intento. No se asigna un número definitivo en el navegador.

## Servicios y límites

| Servicio | Método | Resultado |
| --- | --- | --- |
| `workspace.boot/business/inventory/overview/team` | GET | Contexto administrativo y registros autorizados. |
| `workspace.create_business` | POST | Empresa nueva o elegida, almacén, lista de precios, cliente de mostrador, medios, perfil y terminal nativos. |
| `workspace.save_business/save_settings/create_user/create_product` | POST | Validación y permisos nativos; no publica datos ni envía correos. |
| `workspace.receive_stock/resolve_stock` | POST | Entrada enviada idempotente o bloqueo durable del intento. UUID y payload deben conservarse. |
| `batch.checkout/get_status/abandon/receipt` | POST/GET/POST/POST | Cesta transaccional, recuperación y recibo histórico. |

La moneda predeterminada afecta nuevas entidades. La caja admite la moneda contable de cada empresa y exige la misma moneda para una cesta conjunta. No hay conversión de divisas en el checkout. Los recibos guardan la moneda y zona horaria originales. Los formularios nativos permiten tareas más avanzadas; lotes, series, devoluciones y ajustes requieren sus flujos correspondientes.

No se permiten ventas sin conexión. Una respuesta perdida exige recuperar el mismo UUID o resolverlo con una marca de abandono antes de iniciar otra venta. Resolver no cancela un documento ya enviado ni devuelve pagos externos. La impresión solo abre un diálogo: no confirma papel ni repite la venta.

Idioma inicial español. Ajustes permite español/inglés y formato regional; el manual y los tutoriales permanecen en español. La ayuda nativa y la traducción de ERPNext conservan su cobertura upstream.

## Evidencia reproducible

En Bench con `allow_tests`, maestros ficticios y web/worker activos:

```bash
env/bin/python /ruta/al/repositorio/scripts/test-workspace-http.py --bench /ruta/al/bench
env/bin/python /ruta/al/repositorio/scripts/test-workspace-browser.py --bench /ruta/al/bench --node node
```

El runner del navegador acepta un ejecutable Node Windows y usa Chrome; en CI `OMP_BROWSER_CHANNEL=chromium`. Las claves de sesión/prueba viajan por stdin, se restauran al finalizar y no se publican. Los resultados quedan en `test-results/workspace`, excluidos de Git. Las capturas revisadas del manual tienen un manifest SHA256 exacto; no se autoriza otra imagen por extensión o carpeta.


La selección del negocio conserva el contexto de la empresa para documentos e informes. Clientes y proveedores son maestros compartidos del sitio; sus documentos llevan empresa. Desde Equipo se puede abrir el perfil nativo al pulsar el nombre; Gestionar accesos en Negocios abre la lista autorizada del negocio. La autorización del servidor y los permisos nativos prevalecen sobre cualquier filtro visual.
