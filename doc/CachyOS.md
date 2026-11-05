# PDF a Markdown en CachyOS / KDE Plasma

Esta variante conserva la base de Michael Neivandt y la corrección de saltos
de página de lswingrover. Añade conversión segura, OCR por página y acceso desde
Dolphin. El procesamiento de documentos es local; no necesita cuentas ni APIs.

## Instalación

Dependencias del sistema, mediante los repositorios habituales de CachyOS:

```bash
sudo pacman -Syu --needed git python-pipx tesseract tesseract-data-spa tesseract-data-eng tk kdialog
pipx ensurepath
```

Abre otra terminal después de `pipx ensurepath` si los comandos nuevos no aparecen.
Instala el fork en un entorno Python independiente:

```bash
git clone https://github.com/lgotuzzo/pdfmd.git
cd pdfmd
git switch improvements/cachyos
pipx install '.[ocr]'
pdfmd --version
tesseract --list-langs
pdfmd-kde
```

La última orden instala por usuario un lanzador **PDF a Markdown** y una acción
**Convertir a Markdown (español)** en Dolphin para uno o varios PDF. Cierra y abre
Dolphin si no aparece; revisa Configurar Dolphin → Menú contextual. No requiere
instalar scripts como root. El lanzador usa la ruta absoluta de Python del entorno
pipx, por lo que no depende del PATH de Plasma.

## Uso habitual

Selecciona PDF en Dolphin y usa la acción del menú contextual. Aparece un diálogo
al terminar o si hay errores. Los `.md` se crean junto a sus PDF; los existentes
se conservan y se informa el conflicto. Para otra ubicación usa la interfaz o CLI.

El lanzador del menú de aplicaciones abre la interfaz Tkinter existente. En esa
interfaz selecciona el perfil **Español (CachyOS)**; sus opciones se pueden guardar
para sesiones posteriores. La numeración de página en comentarios está disponible
en la CLI y la conversión directa desde Dolphin.

```bash
pdfmd 'apunte tributario.pdf' --profile es
pdfmd *.pdf --profile es -o markdown/
pdfmd 'documento.pdf' --profile es --preview-only -o vista_previa.md
pdfmd 'documento.pdf' --profile es --ocr off
pdfmd 'documento.pdf' --profile es --lang spa+eng+ita
```

El perfil `es` activa OCR automático, `spa+eng`, separadores y comentarios como
`<!-- pdfmd:page=4 -->`. El número indica la posición física en el PDF, no su
numeración impresa. Los comentarios se pueden buscar en el editor y normalmente
no se ven al renderizar Markdown. Para italiano instala `tesseract-data-ita`.

El OCR automático revisa todas las páginas procesadas. Conserva el texto digital
y reconoce páginas con menos de 50 caracteres y una imagen que ocupa al menos
30% de la página. Una página con abundante texto digital y una sección escaneada
puede requerir `--ocr tesseract`; el modo automático no combina ambos textos
dentro de una misma página. Los PDF solo digitales funcionan sin Tesseract.

## Salida segura y uso con otros programas

Se rechazan destinos existentes salvo `--overwrite`. Tampoco se permite reemplazar
el PDF de entrada, incluso mediante enlaces. Los Markdown se escriben completos
en un archivo temporal y después se publican; no se truncan antes de convertir.
Las carpetas de imágenes existentes también requieren autorización explícita.

```bash
pdfmd documento.pdf --profile es --overwrite
pdfmd documento.pdf --profile es -o - > documento_nuevo.md
pdfmd documento.pdf --profile es -o - | pandoc -f markdown -o documento.docx
```

La redirección `>` la maneja el shell y puede sobrescribir su destino: para la
protección integrada usa `-o nombre.md`. Stdout admite un solo PDF y no admite
`--export-images` ni `--stats`. `--quiet` silencia mensajes normales y conserva
los errores en stderr. Pandoc es opcional y se instala por separado.

## Actualizar y retirar

Desde el clon del fork:

```bash
git pull --ff-only
pipx install --force '.[ocr]'
pdfmd-kde
```

Para quitar la integración y después el programa:

```bash
pdfmd-kde --remove
pipx uninstall pdfmd
```

La integración respeta `XDG_DATA_HOME`; por defecto escribe solamente
`~/.local/share/applications/pdfmd.desktop` y
`~/.local/share/kio/servicemenus/pdfmd.desktop`. No reemplaza entradas ajenas.

## Diagnóstico

- Idioma faltante: comprueba `tesseract --list-langs`; deben aparecer `spa` y `eng`.
- Tkinter ausente: instala `tk` y verifica `python -c 'import tkinter'`.
- Después de una actualización mayor de Python en CachyOS: ejecuta
  `pipx reinstall pdfmd` y vuelve a ejecutar `pdfmd-kde`.
- Las tablas complejas, fórmulas, RUT y cifras reconocidas por OCR requieren
  cotejo con el PDF. El programa no garantiza una transcripción exacta.

Referencias: [menús de Dolphin](https://develop.kde.org/docs/apps/dolphin/service-menus/),
[formato Exec](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html),
[pipx](https://pipx.pypa.io/stable/),
[idioma español](https://archlinux.org/packages/extra/any/tesseract-data-spa/).
