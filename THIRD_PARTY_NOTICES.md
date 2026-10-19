# Licencias y atribuciones

Código original OpenMultiPOS: GPL-3.0-only, según LICENSE. Las referencias a otras herramientas no implican afiliación ni aval.

| Componente | Licencia | Uso en este repositorio |
| --- | --- | --- |
| Frappe Framework | MIT | Dependencia externa de la app, no vendorizada. SHA en upstream.lock.json. |
| ERPNext | GNU GPL v3 | Dependencia externa; sin copia ni modificación del core. Ver license.txt upstream y conservar sus avisos al redistribuirlo. |
| X POS, Ali Raza | MIT | Integración prevista, código inspeccionado, no copiado ni distribuido. SHA en upstream.lock.json. |
| python-qrcode 8.2, Lincoln Loop y colaboradores | BSD-3-Clause | Dependencia runtime para QR SVG; su distribución conserva LICENSE. |
| pypdf | BSD-3-Clause | Verificación de PDFs, solo desarrollo. |
| Ruff | MIT | Herramienta de desarrollo. |
| build / flit_core | MIT | Herramientas de empaquetado. |
| pip-audit | Apache-2.0 | Auditoría de dependencia propia; no prueba seguridad completa upstream. |
| Prettier | MIT | Formato de los assets de demo y runner, solo desarrollo. |
| Playwright | Apache-2.0 | Validación de navegador, solo desarrollo. |
| axe-core / @axe-core/playwright | MPL-2.0 | Auditoría automatizada, solo desarrollo; licencias exactas en paquetes instalados. |

Los símbolos A/N y el layout demo son originales y se distribuyen bajo la licencia del proyecto. No se incluyen fotografías, logotipos ni material comercial de Jaltech ni de las marcas del propietario. Los nombres de productos/proyectos y marcas pertenecen a sus titulares.

Antes de distribuir un conjunto ERPNext/Frappe/X POS, conservar los textos completos y los avisos de todas las dependencias transitivas. Esta tabla no sustituye sus licencias. No se ha auditado toda la cadena upstream.
