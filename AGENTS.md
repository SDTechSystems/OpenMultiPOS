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
