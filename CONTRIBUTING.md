# Contribuir

Leer AGENTS.md, docs/architecture.md y docs/roadmap.md. Abrir cambios pequeños con problema, comportamiento final, validación y límites. Usar únicamente datos ficticios.

Instalar `python -m pip install -e '.[dev]'` en un entorno virtual Python 3.14. Ejecutar unittest, Ruff y build como indica README. Para navegador, `npm ci` y `npm run test:ui` contra una demo desechable; este test registra ventas ficticias. No usar la misma BD de una sesión de evaluación que deba conservarse.

La demo simula ventas; las pruebas Frappe con mocks prueban contratos, no una instalación. Cualquier cambio de transacciones productivas necesita pruebas Bench de permisos, concurrencia y stock nativo. No abrir integraciones DIAN dentro del MVP.

Código propio bajo GPL-3.0-only. Conservar licencias/atribuciones y describir procedencia de recursos. Logotipos reales no son recursos de ejemplo.
