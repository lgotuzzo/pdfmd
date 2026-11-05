# Uso local en CachyOS

Objetivo: mantener el conversor local y facilitar PDF a Markdown en KDE/Dolphin.
Se conserva Python/Tkinter; no se añade servidor, nube ni dependencia de IA.

La base es lswingrover/pdfmd 95e3b15, con su corrección de separadores.
Se elige ampliar CLI e integración KDE antes que rehacer la interfaz o empaquetar
una aplicación web: reutiliza el motor existente y requiere menos mantenimiento.

Alcance:
- CLI rechaza destinos existentes por defecto, admite --overwrite y stdout (-o -).
- OCR auto decide por página; conserva texto digital y reconoce escaneos tardíos.
- Si una página requiere OCR sin motor/idioma disponible, falla con diagnóstico.
- Perfil CLI español: OCR auto, spa+eng, separadores y referencias de página.
- Integración por usuario: lanzador y menú Dolphin, sin sudo ni modificar el sistema.
- Documentación CachyOS con pipx y dependencias instaladas mediante pacman.

Límites: no se promete reconstrucción exacta de tablas, fórmulas ni manuscritos.
Se prueban conversiones, errores y rutas con espacios; la sesión no dispone de KDE.
