# Diseño del espacio de trabajo

## Usuarios y tareas

Dos administradores gestionan dos negocios desde Windows, con una impresora térmica y un lector HID existentes. Necesitan encontrar una herramienta, reconocer el negocio activo y terminar la tarea sin conocer los nombres internos de ERPNext. El primer resultado útil es crear un producto, registrar existencias y venderlo con un recibo compacto.

## Decisiones visuales

- Fondo de trabajo gris azulado `#f3f6fa`, papel blanco `#ffffff`, texto `#182536`, navegación azul `#193954`, acción azul `#245fa4` y aviso ámbar `#8c4b12`.
- Segoe UI Variable y Segoe UI como fuentes locales de Windows. Encabezados de 26/20 px, cuerpo de 15 px y tablas de 14 px. Importes alineados a la derecha con números tabulares.
- Menú lateral de 224 px, selector de negocio en la cabecera y área de tarea a la derecha. Iconos SVG con etiqueta visible. Las herramientas frecuentes tienen nombre y acción concreta.
- Formularios en una columna de lectura, con grupos cuando corresponda. Tablas para registros. No convertir cada dato o función en una tarjeta ni mostrar indicadores sin datos reales.
- Ayuda por opción, acceso al manual en el mismo lugar y tutoriales cortos que se pueden omitir y repetir. Los errores conservan datos y explican el siguiente paso.

```text
Menú lateral    Negocio activo                  Buscar herramienta
                Título de la tarea             Ayuda
                Filtros y acción principal
                Tabla o formulario
```

La diferencia respecto de una portada genérica es la prioridad de las tareas de operación. El selector controla el contexto. La pantalla inicial muestra qué necesita configuración y qué puede hacer el usuario. No añade gráficos decorativos, promesas de compatibilidad ni datos simulados presentados como reales.

## Alcance y escritura

Idioma español, COP y America/Bogota. Solo el equipo de impresión/lectura configurado. Escribir verbos y nombres que usa el administrador. Aplicar frontend-design, onboard, accessibility y unslop. Los datos de instalación, identidades, marcas, NIT y contactos se introducen en el servidor privado y no forman parte de fixtures, código, issues o capturas públicas.
