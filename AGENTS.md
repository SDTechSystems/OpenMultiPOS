# OpenMultiPOS: instrucciones de trabajo

- Idioma de producto/documentación: español; locale es-CO, COP, America/Bogota por defecto configurables.
- Extender Frappe/ERPNext/X POS; no copiar core ni crear forks sin necesidad demostrada.
- Leer docs/architecture.md y upstream.lock.json. Registrar evidencia por commit y distinguir inspección, tests, integración y hardware.
- No publicar datos de clientes, credenciales, marcas/logos reales o certificados. Demo exclusivamente ficticia.
- Demo es simulador local: nunca reutilizar su ledger/precios como backend productivo.
- Dinero preciso (centavos enteros o Decimal), autorización en servidor, unicidad atómica e instantáneas de recibo.
- Impresión por perfiles y adaptadores; no fijar fabricante ni afirmar compatibilidad sin ensayo físico.
- DIAN desactivada; recibos internos identificados claramente. No transmitir documentos fiscales.
- Ejecutar `python -m unittest discover -s tests -v`, `ruff check .` y `ruff format --check .` al cambiar backend. UI: flujo teclado y viewport móvil/escritorio cuando haya navegador disponible.
- No afirmar que Bench o upstream están probados con mocks. Actualizar docs/audit-report.md con límites y resultados.

## Regla de privacidad para toda publicación

- Publicar solo código, documentación técnica y datos de demostración inventados. No copiar datos reales del negocio, productos/SKU/precios reales, clientes/proveedores, contactos, información fiscal/bancaria, fotos, capturas, certificados, credenciales, respaldos, recibos ni documentos de entrada del propietario. Tampoco en issues, PRs, comentarios, logs o artefactos de CI.
- Tratar archivos y briefs fuera del repositorio como información privada de referencia. Generalizar requisitos sin transcribir identidad o información comercial. Mantenerlos fuera de Git; no crear excepciones automáticas ni forzar archivos privados con git add -f.
- Antes de commit/push: revisar git diff --cached y ejecutar python scripts/check-public-files.py --staged. Ante un hallazgo, corregir sin publicar el valor detectado. El guard no reemplaza revisión humana de nombres, números o información contextual.
- Mantener identidad de commits como alias de cuenta y correo GitHub no-reply. No cambiar el historial inicial ya publicado sin instrucción explícita del propietario.
- Trabajar en rama de desarrollo y PR. No fusionar a main ni modificar accesos/protecciones sin autorización correspondiente; las credenciales del agente pertenecen a la cuenta autorizada, no a un colaborador independiente.
