# Actividad AWS: guía del proyecto

Esta guía sirve como índice para recorrer el proyecto. El enunciado original está en [Actividad AWS.pdf](Actividad%20AWS.pdf) y los integrantes están en [INTEGRANTES.txt](INTEGRANTES.txt).

## Documentos de consulta

- [Teoría, preguntas, respuestas y explicaciones](documento/RESPUESTAS_Y_EXPLICACIONES.md): desarrollo conceptual de los seis puntos.
- [Costos](documento/COSTOS.md): supuestos, estimaciones y componentes que pueden generar cobros.

Este README completa los tres documentos principales de la entrega. Las capturas y los logs dentro de `evidencias/` son evidencias originales del trabajo.

## Estructura

| Ruta | Contenido |
|---|---|
| `recursos_cada_punto/punto1_secrets_manager/` | Scripts, política IAM y recursos del punto 1: Secrets Manager. |
| `recursos_cada_punto/punto2_terraform_sdk_cli/` | Ejemplos del punto 2 con Terraform, Boto3, AWS CLI e IAM. |
| `recursos_cada_punto/punto3_documentdb/` | Despliegue y limpieza de Amazon DocumentDB. |
| `recursos_cada_punto/punto4_neptune/` | Despliegue de Neptune, consultas y archivos de grafo. |
| `recursos_cada_punto/punto5_redshift/` | Redshift, consultas SQL, datos de ejemplo y verificación local. |
| `recursos_cada_punto/punto6_glue_catalog/` | Glue Data Catalog, crawler y datos de ejemplo para Athena. |
| `evidencias/punto1/` … `evidencias/punto6/` | Pantallazos, logs y resultados correspondientes a cada punto. |
| `comun/` | Funciones Python compartidas por los scripts. |
| `documento/` | Los dos documentos temáticos enlazados arriba. |
| `pyproject.toml`, `uv.lock` | Dependencias y configuración del entorno Python. |

## Preparar el entorno

Desde la raíz, en PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
uv sync
```

Si PowerShell bloquea la activación, puede ejecutarse directamente con `uv run` sin activar el entorno. Algunos ejemplos, siempre desde la raíz:

```powershell
uv run python recursos_cada_punto/punto1_secrets_manager/secrets_manager.py todo
uv run python recursos_cada_punto/punto3_documentdb/documentdb.py todo
uv run python recursos_cada_punto/punto4_neptune/neptune_grafo.py todo
uv run python recursos_cada_punto/punto5_redshift/redshift_serverless.py todo
uv run python recursos_cada_punto/punto6_glue_catalog/glue_catalog.py todo
```

Para retirar recursos de AWS, usa `limpiar` en el script correspondiente y revisa sus opciones antes de ejecutarlo. El punto 2 contiene alternativas independientes en `recursos_cada_punto/punto2_terraform_sdk_cli/terraform/`, `sdk_boto3/` y `amazon_cli/`; sus scripts se llaman `ejecutar_terraform.py`, `desplegar.py` y `desplegar.sh`. Los comandos de AWS requieren credenciales y permisos configurados; consulta los scripts del punto respectivo.

## Evidencias

Las evidencias se conservan en `evidencias/puntoN/`, separadas por punto. No se deben mover ni borrar las capturas al reorganizar la documentación. Los archivos de estado, credenciales y cachés locales se excluyen mediante `.gitignore`.

