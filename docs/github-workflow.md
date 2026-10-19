# Cómo se guarda y protege el proyecto en GitHub

- **Repositorio**: la carpeta del proyecto y su historial alojados en GitHub. Este repositorio es público: se puede leer/copiar su código, pero eso no concede acceso de escritura.
- **Commit**: una versión guardada con identificador y autor. Los commits de desarrollo usan alias y correo GitHub no-reply.
- **Rama**: una línea de trabajo. Los cambios iniciales están en `codex/foundation-and-roadmap`; no se vuelven estables solo por enviarlos a GitHub.
- **main**: la rama estable. Se protege para recibir cambios por PR y con comprobaciones correctas, sin sobrescrituras forzadas ni eliminación.
- **Pull request / PR**: propuesta revisable para incorporar una rama en otra. [PR #1](https://github.com/JSX2011/OpenMultiPOS/pull/1) contiene el primer incremento. No está fusionado.
- **Push**: subir commits de una rama. **Merge**: incorporar los cambios de un PR a main; es una acción distinta y se decide explícitamente.
- **Checks / CI**: comprobaciones automáticas de privacidad, Python y navegador. Deben pasar antes de integrar.

El acceso de escritura se administra en los permisos del repositorio, no mediante el carácter público del código. CODEOWNERS identifica al mantenedor para solicitudes de revisión, pero no otorga ni revoca permisos. Un agente que usa una cuenta autorizada no es por sí mismo un colaborador GitHub diferente.

No agregar colaboradores, cambiar visibilidad ni fusionar PRs sin autorización. Evitar exigir a un único propietario que apruebe su propio PR desde otra identidad: se usan PR, checks y revisión explícita de la propuesta.

Antes de cada publicación: revisar archivos/diff, usar únicamente datos inventados y ejecutar `python scripts/check-public-files.py --staged`. Instalar hooks locales con `git config --local core.hooksPath .githooks`. No subir documentos, fotografías, datos comerciales, credenciales ni respaldos a issues, comentarios o artefactos.
