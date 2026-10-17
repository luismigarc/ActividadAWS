# Punto 6 – AWS Glue Data Catalog

## Qué hace el script
`glue_catalog.py` automatiza todo con Boto3 y deja la evidencia en `evidencias/punto6/`:

| Paso | Acción | Evidencia |
|---|---|---|
| `crear` | Bucket S3 privado, sube `datos/ventas_2026-09.csv` (25 registros) a `s3://<bucket>/ventas/mes=2026-09/`, base de datos `taller_ventas_db`, rol IAM del crawler y workgroup de Athena con límite de 10 MB por consulta | `01..04_*.json`, `politica_rol_crawler.json` |
| `crawler` | Crea y ejecuta el crawler. Guarda el esquema inferido y lo compara con el esperado | `esquema_inferido.csv` |
| `corregir` | Corrige los tipos mal inferidos en la tabla **y en sus particiones** (`glue.update_table` / `update_partition`). Muestra en Athena el antes/después de `codigo_postal` | `correcciones_esquema.csv`, `antes_/despues_correccion_codigos.csv` |
| `consultar` | Athena: filtro (`WHERE`) y agrupaciones (`GROUP BY`) | `consulta_filtro.csv`, `consulta_agrupacion*.csv` |
| `agregar` | Sube 10 registros nuevos (`mes=2026-10`), vuelve a ejecutar el crawler y comprueba la nueva partición, que el esquema corregido se mantiene y que el conteo pasa de 25 a 35 | `particiones_en_catalogo.csv`, `conteo_*_de_agregar.csv` |
| `manual` | Crea la misma tabla con DDL (`CREATE EXTERNAL TABLE` + `MSCK REPAIR TABLE`) para comparar | `ddl_tabla_manual.sql`, `consulta_tabla_manual.csv` |
| `costos` | Bytes escaneados reales + Price List API | `estimacion_costos.csv`, `precios_api.json` |
| `limpiar` | Borra workgroup, crawler, base de datos, rol y bucket, y comprueba que no existan | `verificacion_eliminacion.csv` |

```bash
uv run python punto6_glue_catalog/glue_catalog.py todo
# (tome capturas en la consola: tabla en Glue, crawler, Athena)
uv run python punto6_glue_catalog/glue_catalog.py limpiar
```

## Datos
`datos/generar_datos.py` genera (con semilla fija) dos CSV con columnas
`id_venta, fecha, ciudad, codigo_postal, producto, categoria, cantidad, precio_unitario, cliente_vip`.
Están en carpetas estilo Hive (`mes=AAAA-MM`), por lo que el crawler crea la columna de partición `mes`.

## Errores de inferencia que se corrigen
| Columna | Lo que suele inferir el crawler | Correcto | Por qué |
|---|---|---|---|
| `codigo_postal` | `bigint` | `string` | `055420` perdería el cero inicial; no se hacen cálculos con él |
| `fecha` | `string` | `date` | Permite filtros y funciones de fecha |
| `precio_unitario` | `double` | `decimal(12,2)` | Dinero: decimal exacto, no punto flotante |
| `cantidad` | `bigint` | `int` | Rango pequeño (opcional) |

El script compara contra `ESQUEMA_ESPERADO`, de modo que corrige lo que el crawler haya inferido mal en su caso.

## Configuración del crawler
- Origen: `s3://<bucket>/ventas/`
- `SchemaChangePolicy.UpdateBehavior = LOG`: cuando se vuelve a ejecutar, **no sobrescribe** el esquema corregido a mano.
- `CrawlerOutput.Partitions.AddOrUpdateBehavior = InheritFromTable`: las particiones nuevas heredan el esquema corregido.
- Rol: `AWSGlueServiceRole` + `s3:GetObject` solo en `ventas/*` y `s3:ListBucket` en el bucket.

## Crawler vs tabla manual
| | Crawler | DDL manual |
|---|---|---|
| Esquema | Lo infiere (puede equivocarse con los tipos) | Lo define usted exactamente |
| Particiones nuevas | Las detecta al volver a ejecutarlo | Requiere `MSCK REPAIR TABLE`, `ALTER TABLE ADD PARTITION` o partition projection |
| Cambios de esquema | Los detecta (o los registra en el log si se usa LOG) | Manuales |
| Costo | DPU-hora (mínimo 10 min por ejecución) | DDL en Athena: gratis |
| Ideal para | Datos nuevos o desconocidos, muchas carpetas | Esquemas conocidos y estables, control total |

## Credenciales
Este punto **no usa contraseñas de aplicación**: S3, Glue y Athena se autorizan con IAM (la identidad de AWS CLI del usuario y el rol del crawler, asumido por Glue mediante STS con credenciales temporales). No existe un usuario o contraseña de base de datos que guardar, así que **no se crea un secreto**. Solo haría falta Secrets Manager si el crawler usara una *Glue Connection* JDBC (por ejemplo, contra RDS).
