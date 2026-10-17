# Estado de la Actividad AWS (16/10/2026)

Este archivo es la lista de control de la entrega. El estado se actualiza solo a partir de evidencias
guardadas en `evidencias/puntoN/`; el código preparado no cuenta como ejecución completada.

| Punto | Estado | Evidencia |
|---|---|---|
| 1 – Secrets Manager | Código listo, **pendiente de ejecutar** | – |
| 2 – Terraform / Boto3 / CLI | Código listo, **pendiente de ejecutar**. Ya se creó `user_cli` con su política (`evidencias/punto2/`) | parcial |
| 3 – DocumentDB | Código listo, **pendiente de ejecutar** | – |
| 4 – Neptune | **Hecho** y recursos eliminados (verificado) | `evidencias/punto4/` |
| 5 – Redshift | **Hecho** y recursos eliminados (verificado) | `evidencias/punto5/` |
| 6 – Glue Data Catalog | **Hecho** y recursos eliminados (verificado) | `evidencias/punto6/` |

- Documento con toda la evidencia y las respuestas teóricas: `documento/EVIDENCIAS_Actividad_AWS.docx`
  (se regenera con `uv run python documento/generar_documento.py`).
- Respuestas teóricas y de costos de los 6 puntos: `documento/RESPUESTAS_TEORICAS.md`.
- Cómo ejecutar cada punto: `README.md` de la raíz y el `README.md` de cada carpeta.

## Para ejecutar los puntos pendientes en otra cuenta de AWS
1. WSL/Linux con AWS CLI v2, `uv` y Terraform. Configure un perfil admin (no la cuenta raíz).
2. `uv sync` en la raíz del proyecto (crea `.venv`; no viene en el zip).
3. Los nombres de los recursos incluyen el número de cuenta, así que los scripts funcionan sin cambios.
4. Ejecute siempre `limpiar` al terminar cada punto.

Orden sugerido: punto 1 (~2 min) → punto 3 (~15 min) → punto 2 (~40 min: crea y borra lo mismo 3 veces).
