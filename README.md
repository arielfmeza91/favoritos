# Favoritos para NVDA

Complemento para [NVDA](https://www.nvaccess.org/) que permite guardar enlaces
(sitios web), carpetas y accesos a archivos o programas, y acceder a ellos
rápidamente desde un submenú **Favoritos** dentro del menú Herramientas de NVDA.

## Instalación

Descarga el archivo `.nvda-addon` desde la sección
[Releases](../../releases) de este repositorio y ábrelo con NVDA en ejecución
para instalarlo.

## Uso

- **Herramientas → Favoritos → Añadir a favoritos...**: guarda un enlace,
  carpeta o acceso a archivo/programa.
- **Herramientas → Favoritos → Editar o eliminar favoritos...**: elige una
  categoría, edita el nombre/ruta de un elemento guardado o elimínalo.
- **Herramientas → Favoritos → Enlaces / Carpetas / Accesos a archivos o
  programas**: abre cualquiera de tus elementos guardados.
- **Herramientas → Favoritos → Más usados**: los 10 favoritos que más abres,
  de cualquier categoría.
- **NVDA+Mayús+F** (desde un navegador): añade la página actual a favoritos,
  con título y URL ya rellenados.
- Cada enlace puede abrirse con un navegador concreto (campo **Abrir con**) o
  con el predeterminado.

Los favoritos se guardan en `favoritos.json`, dentro de la carpeta de
configuración de tu perfil de NVDA.

## Compilar el paquete desde el código fuente

El código fuente del complemento vive en `addon-source/`. Para generar el
archivo `.nvda-addon` a partir de él:

```bash
python -c "
import zipfile, os
base = 'addon-source'
out = 'favoritos-1.1.0.nvda-addon'
files = [
    ('manifest.ini', 'manifest.ini'),
    (os.path.join('globalPlugins','favoritos','__init__.py'), os.path.join('globalPlugins','favoritos','__init__.py')),
    (os.path.join('doc','es','readme.html'), os.path.join('doc','es','readme.html')),
    (os.path.join('doc','en','readme.html'), os.path.join('doc','en','readme.html')),
]
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for rel, arc in files:
        z.write(os.path.join(base, rel), arc.replace(os.sep, '/'))
"
```

## Licencia

Todos los derechos reservados por el autor.
