# Evidencias punto6


## Paso 1 - Recursos base (S3, Glue Database, rol del crawler, workgroup Athena)  
_2026-10-15 19:18:42_

- Evidencia: `01_identidad_usada.json` (2026-10-15 19:18:58)
- Bucket privado creado: s3://taller-ingdata-p6-129898048658-us-east-1 (Block Public Access activado)
- Subido ventas_2026-09.csv (25 registros) a s3://taller-ingdata-p6-129898048658-us-east-1/ventas/mes=2026-09/ventas_2026-09.csv
- Evidencia: `02_s3_objetos.json` (2026-10-15 19:19:50)
- Evidencia: `03_glue_database.json` (2026-10-15 19:20:08)
- Archivo: `politica_rol_crawler.json`
- Rol del crawler: arn:aws:iam::129898048658:role/taller-ingdata-p6-glue-crawler-role (AWSGlueServiceRole + lectura del prefijo ventas/)
- Evidencia: `04_athena_workgroup.json` (2026-10-15 19:20:59)

## Paso 2 - Crawler: descubrimiento del esquema  
_2026-10-15 19:20:59_

- Evidencia: `05_crawler_configuracion.json` (2026-10-15 19:21:16)
- Evidencia: `06_crawler_ejecucion_inicial.json` (2026-10-15 19:22:16)
- Evidencia: `07_crawler_metricas_inicial.json` (2026-10-15 19:22:16)
- Evidencia: `08_esquema_inferido_tabla.json` (2026-10-15 19:22:34)

**esquema_inferido** - Esquema que infirió el crawler vs el esperado

| columna | tipo_inferido | tipo_esperado | correcto |
|---|---|---|---|
| id_venta | bigint | bigint | sí |
| fecha | string | date | NO |
| ciudad | string | string | sí |
| codigo_postal | bigint | string | NO |
| producto | string | string | sí |
| categoria | string | string | sí |
| cantidad | bigint | int | NO |
| precio_unitario | double | decimal(12,2) | NO |
| cliente_vip | boolean | boolean | sí |


**particiones_inferidas** 

| clave | tipo |
|---|---|
| mes | string |

- Clasificación: csv, SerDe: org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe, skip.header.line.count=1

## Paso 3 - Revisión y corrección del esquema  
_2026-10-15 19:22:34_

- Evidencia: `09_athena_antes_correccion_codigos.json` (2026-10-15 19:23:27)

**antes_correccion_codigos** - Códigos postales con el tipo inferido (escaneado: 1666 bytes)

| ciudad | codigo_postal |
|---|---|
| Barranquilla | 80001 |
| Bogota | 110111 |
| Cali | 760001 |
| Envigado | 55420 |
| Medellin | 50021 |


**correcciones_esquema** - Cambios aplicados con glue.update_table

| columna | tipo_inferido | tipo_corregido |
|---|---|---|
| fecha | string | date |
| codigo_postal | bigint | string |
| cantidad | bigint | int |
| precio_unitario | double | decimal(12,2) |

- Partición ['2026-09'] actualizada con el esquema corregido
- Evidencia: `10_esquema_corregido_tabla.json` (2026-10-15 19:23:28)
- Evidencia: `11_athena_despues_correccion_codigos.json` (2026-10-15 19:23:47)

**despues_correccion_codigos** - Códigos postales con tipo string (escaneado: 1666 bytes)

| ciudad | codigo_postal |
|---|---|
| Barranquilla | 080001 |
| Bogota | 110111 |
| Cali | 760001 |
| Envigado | 055420 |
| Medellin | 050021 |

- Antes: [['Barranquilla', '80001'], ['Bogota', '110111'], ['Cali', '760001'], ['Envigado', '55420'], ['Medellin', '50021']] | Después: [['Barranquilla', '080001'], ['Bogota', '110111'], ['Cali', '760001'], ['Envigado', '055420'], ['Medellin', '050021']]
- Evidencia: `12_athena_tipos_en_athena.json` (2026-10-15 19:24:38)

**tipos_en_athena** - Tipos que ve Athena tras la corrección (escaneado: 1666 bytes)

| t_fecha | t_precio | t_cp | t_cant |
|---|---|---|---|
| date | decimal(12,2) | varchar | integer |


## Paso 4 - Consultas en Athena  
_2026-10-15 19:24:38_

- Evidencia: `13_athena_consulta_filtro.json` (2026-10-15 19:25:13)

**consulta_filtro** - ¿Qué ventas de Tecnología tuvieron 3 o más unidades? (escaneado: 1666 bytes)

| id_venta | fecha | ciudad | producto | cantidad | precio_unitario |
|---|---|---|---|---|---|
| 22 | 2026-09-01 | Bogota | Portatil | 5 | 3499.90 |
| 8 | 2026-09-02 | Cali | Mouse | 5 | 59.90 |
| 4 | 2026-09-07 | Barranquilla | Mouse | 5 | 59.90 |
| 21 | 2026-09-07 | Barranquilla | Mouse | 3 | 59.90 |
| 19 | 2026-09-15 | Medellin | Audifonos | 4 | 249.00 |
| 1 | 2026-09-16 | Envigado | Mouse | 3 | 59.90 |
| 10 | 2026-09-21 | Envigado | Portatil | 3 | 3499.90 |
| 15 | 2026-09-21 | Bogota | Portatil | 3 | 3499.90 |
| 17 | 2026-09-22 | Cali | Monitor | 4 | 899.50 |
| 25 | 2026-09-22 | Cali | Audifonos | 4 | 249.00 |
| 2 | 2026-09-25 | Bogota | Audifonos | 3 | 249.00 |
| 5 | 2026-09-28 | Cali | Mouse | 4 | 59.90 |

- Evidencia: `14_athena_consulta_agrupacion.json` (2026-10-15 19:25:32)

**consulta_agrupacion** - Ventas totales, unidades y ticket promedio por categoría (escaneado: 1666 bytes)

| categoria | num_ventas | unidades | total_ventas | ticket_promedio |
|---|---|---|---|---|
| Tecnologia | 14 | 50 | 46651.70 | 3332.26 |
| Muebles | 7 | 29 | 27085.85 | 3869.41 |
| Papeleria | 4 | 14 | 109.90 | 27.48 |

- Evidencia: `15_athena_consulta_agrupacion_ciudad.json` (2026-10-15 19:25:51)

**consulta_agrupacion_ciudad** - Ventas por ciudad y tipo de cliente (escaneado: 1666 bytes)

| ciudad | cliente_vip | num_ventas | total |
|---|---|---|---|
| Barranquilla | false | 3 | 599.00 |
| Barranquilla | true | 2 | 6012.75 |
| Bogota | false | 2 | 11246.70 |
| Bogota | true | 1 | 17499.50 |
| Cali | false | 5 | 6833.06 |
| Cali | true | 2 | 6194.00 |
| Envigado | false | 4 | 8092.06 |
| Envigado | true | 3 | 13924.40 |
| Medellin | false | 3 | 3445.98 |


## Paso 5 - Agregar registros y actualizar el catálogo  
_2026-10-15 19:25:51_

- Evidencia: `16_athena_conteo_antes_de_agregar.json` (2026-10-15 19:26:42)

**conteo_antes_de_agregar** - Registros por partición antes (escaneado: 1666 bytes)

| mes | registros |
|---|---|
| 2026-09 | 25 |

- Subido ventas_2026-10.csv (10 registros nuevos) a s3://taller-ingdata-p6-129898048658-us-east-1/ventas/mes=2026-10/ventas_2026-10.csv
- Evidencia: `17_crawler_ejecucion_tras_agregar.json` (2026-10-15 19:27:57)
- Evidencia: `18_crawler_metricas_tras_agregar.json` (2026-10-15 19:27:57)

**particiones_en_catalogo** - Particiones registradas tras volver a ejecutar el crawler

| valores | ubicacion | columnas_iguales_a_tabla |
|---|---|---|
| ['2026-10'] | s3://taller-ingdata-p6-129898048658-us-east-1/ventas/mes=2026-10/ | True |
| ['2026-09'] | s3://taller-ingdata-p6-129898048658-us-east-1/ventas/mes=2026-09/ | True |

- ¿El crawler conservó el esquema corregido? sí (SchemaChangePolicy.UpdateBehavior=LOG)
- Evidencia: `19_athena_conteo_despues_de_agregar.json` (2026-10-15 19:28:17)

**conteo_despues_de_agregar** - Registros por partición después (escaneado: 2392 bytes)

| mes | registros |
|---|---|
| 2026-09 | 25 |
| 2026-10 | 10 |

- Total de registros: 25 -> 35
- Evidencia: `20_athena_consulta_poda_particion.json` (2026-10-15 19:28:36)

**consulta_poda_particion** - Solo lee la partición 2026-10 (menos bytes escaneados) (escaneado: 726 bytes)

| ventas_octubre |
|---|
| 10 |


## Paso 6 - Tabla creada manualmente (DDL) para comparar con el crawler  
_2026-10-15 19:28:36_

- Archivo: `ddl_tabla_manual.sql`
- Evidencia: `21_tabla_manual.json` (2026-10-15 19:29:31)
- Evidencia: `22_athena_consulta_tabla_manual.json` (2026-10-15 19:29:49)

**consulta_tabla_manual** - Misma agrupación sobre la tabla manual (escaneado: 2392 bytes)

| categoria | num_ventas | total_ventas |
|---|---|---|
| Tecnologia | 16 | 54649.10 |
| Muebles | 11 | 38081.78 |
| Papeleria | 8 | 200.60 |


## Paso 7 - Estimación de costos  
_2026-10-15 19:29:49_

- Evidencia: `23_precios_api.json` (2026-10-15 19:30:41)

**estimacion_costos** - Precios de referencia us-east-1; ver precios_api para los valores de la API

| componente | uso | costo_estimado_usd |
|---|---|---|
| Athena (bytes reales escaneados) | 17172 B en 12 consultas | - |
| Athena (facturable, mín. 10 MB/consulta con datos) | 100 MB | $0.0005 |
| Crawler (2 ejecuciones x 10 min mín. x ~2 DPU) | 0.44 USD/DPU-h | $0.2933 |
| Glue Data Catalog (2 tablas, 2-4 particiones) | < 1 millón de objetos | $0.00 (capa gratuita) |
| S3 almacenamiento (CSV + resultados Athena) | 2392 B | < $0.0001/mes |
| S3 solicitudes PUT/GET | decenas | < $0.001 |

- Evidencia: `24_crawler_metricas_finales.json` (2026-10-15 19:30:59)

## Limpieza - eliminación de recursos y verificación  
_2026-10-15 19:36:39_

- Eliminado: workgroup Athena
- Eliminado: crawler
- Eliminado: base de datos Glue (y sus tablas)
- Eliminado: rol IAM
- Eliminado: bucket S3

**verificacion_eliminacion** - Comprobación posterior a la eliminación

| recurso | estado |
|---|---|
| Workgroup Athena | no existe (InvalidRequestException) |
| Crawler | no existe (EntityNotFoundException) |
| Base de datos Glue | no existe (EntityNotFoundException) |
| Rol IAM | no existe |
| Bucket S3 | no existe |

