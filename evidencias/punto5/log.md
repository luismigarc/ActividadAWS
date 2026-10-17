# Evidencias punto5


## Paso 1 - Despliegue de Redshift Serverless  
_2026-10-15 20:04:28_

- Evidencia: `01_identidad_usada.json` (2026-10-15 20:04:46)
- Bucket privado: s3://taller-ingdata-p5-129898048658-us-east-1
- Evidencia: `02_rol_copy_confianza.json` (2026-10-15 20:06:10)
- Evidencia: `03_rol_copy_permisos.json` (2026-10-15 20:06:11)
- Evidencia: `04_namespace.json` (2026-10-15 20:06:31)
- Secreto del administrador (administrado por Redshift): arn:aws:secretsmanager:us-east-1:129898048658:secret:redshift!taller-ingdata-ns-admin_taller-FPwVYy
- Evidencia: `05_secreto_admin_metadatos.json` (2026-10-15 20:06:47)
- Evidencia: `06_workgroup.json` (2026-10-15 20:08:27)
- Workgroup taller-ingdata-wg: capacidad base 4 RPU, acceso público=False, endpoint=taller-ingdata-wg.129898048658.us-east-1.redshift-serverless.amazonaws.com
- Evidencia: `07_limite_uso.json` (2026-10-15 20:08:28)
- Límite de uso: 4 RPU-hora/día (alerta en log) como control de costos

## Paso 2 - Subida a S3, creación de tablas y COPY  
_2026-10-15 20:08:28_

- Evidencia: `08_s3_objetos.json` (2026-10-15 20:08:44)
- CSV subidos a s3://taller-ingdata-p5-129898048658-us-east-1/redshift/datos/
- Evidencia: `09_dataapi_crear_tablas.json` (2026-10-15 20:09:18)
- Evidencia: `10_dataapi_copy_desde_s3.json` (2026-10-15 20:09:54)
- Evidencia: `11_dataapi_conteo_filas_cargadas.json` (2026-10-15 20:10:28)

**conteo_filas_cargadas** - Filas cargadas por COPY (esperado: 20, 10, 120)

| tabla | filas |
|---|---|
| clientes | 20 |
| pedidos | 120 |
| productos | 10 |

- Evidencia: `12_dataapi_historial_copy.json` (2026-10-15 20:11:01)

**historial_copy** - Historial de cargas COPY

| query_id | table_name | file_format | loaded_rows | loaded_bytes | duration | status |
|---|---|---|---|---|---|---|
| 1610 | pedidos | Text | 120 | 3186 | 459355 | completed |
| 1597 | productos | Text | 10 | 373 | 331816 | completed |
| 1588 | clientes | Text | 20 | 1008 | 505703 | completed |


## Inspección de componentes (tablas, distribución, ordenamiento)  
_2026-10-15 20:11:01_

- Evidencia: `13_dataapi_svv_table_info.json` (2026-10-15 20:11:36)

**svv_table_info** - Estilo de distribución y llave de ordenamiento de cada tabla

| tabla | diststyle | sortkey1 | tbl_rows | bloques_1mb |
|---|---|---|---|---|
| clientes | ALL | AUTO(SORTKEY) | 20 | 16 |
| pedidos | KEY(id_cliente) | fecha_pedido | 120 | 288 |
| productos | ALL | AUTO(SORTKEY) | 10 | 14 |


## Paso 3 - Consultas (filtro, unión, agregación)  
_2026-10-15 20:11:36_

- **q1_filtro** - ¿Qué pedidos del tercer trimestre de 2026 (jul-sep) fueron de 3 o más unidades?
- Evidencia: `14_dataapi_q1_filtro.json` (2026-10-15 20:12:13)

**q1_filtro** - ¿Qué pedidos del tercer trimestre de 2026 (jul-sep) fueron de 3 o más unidades?

| id_pedido | fecha_pedido | id_cliente | id_producto | cantidad | descuento_pct |
|---|---|---|---|---|---|
| 1059 | 2026-07-16 | 19 | 5 | 5 | 0 |
| 1104 | 2026-07-16 | 11 | 8 | 3 | 5 |
| 1079 | 2026-07-18 | 6 | 6 | 3 | 10 |
| 1006 | 2026-07-25 | 16 | 3 | 5 | 15 |
| 1019 | 2026-07-25 | 15 | 6 | 4 | 5 |
| 1047 | 2026-07-28 | 12 | 7 | 5 | 0 |
| 1092 | 2026-07-28 | 12 | 4 | 3 | 0 |
| 1068 | 2026-08-03 | 14 | 1 | 5 | 10 |
| 1087 | 2026-08-11 | 15 | 4 | 3 | 15 |
| 1071 | 2026-08-15 | 19 | 4 | 3 | 15 |
| 1073 | 2026-08-16 | 6 | 9 | 3 | 15 |
| 1004 | 2026-08-21 | 15 | 1 | 3 | 0 |
| 1020 | 2026-08-25 | 19 | 10 | 3 | 0 |
| 1120 | 2026-09-05 | 20 | 2 | 3 | 10 |
| 1078 | 2026-09-09 | 16 | 1 | 3 | 15 |
| 1024 | 2026-09-13 | 15 | 9 | 4 | 0 |
| 1100 | 2026-09-21 | 18 | 8 | 4 | 15 |
| 1035 | 2026-09-23 | 4 | 10 | 3 | 0 |
| 1064 | 2026-09-29 | 18 | 6 | 5 | 0 |

- ¿Coincide con la verificación local en SQLite? sí
- **q2_union** - ¿Cuáles son los 10 pedidos de mayor valor neto hechos por clientes de Medellín, con el nombre del cliente y del producto?
- Evidencia: `15_dataapi_q2_union.json` (2026-10-15 20:12:46)

**q2_union** - ¿Cuáles son los 10 pedidos de mayor valor neto hechos por clientes de Medellín, con el nombre del cliente y del producto?

| id_pedido | fecha_pedido | cliente | producto | cantidad | descuento_pct | valor_neto |
|---|---|---|---|---|---|---|
| 1078 | 2026-09-09 | Pablo Vargas | Portatil 14 | 3 | 15 | 8922450 |
| 1105 | 2026-04-04 | Diego Restrepo | Portatil 14 | 3 | 15 | 8922450 |
| 1062 | 2026-04-15 | Pablo Vargas | Portatil 14 | 2 | 0 | 6998000 |
| 1006 | 2026-07-25 | Pablo Vargas | Monitor 27 | 5 | 15 | 5482500 |
| 1007 | 2026-04-17 | Diego Restrepo | Escritorio en L | 4 | 0 | 4600000 |
| 1041 | 2026-04-17 | Isabel Vargas | Escritorio en L | 4 | 0 | 4600000 |
| 1095 | 2026-06-21 | Isabel Vargas | Escritorio en L | 3 | 5 | 3277500 |
| 1058 | 2026-05-29 | Pablo Vargas | Portatil 14 | 1 | 10 | 3149100 |
| 1107 | 2026-08-10 | Carla Lopez | Escritorio en L | 2 | 0 | 2300000 |
| 1085 | 2026-07-07 | Diego Restrepo | Escritorio en L | 2 | 15 | 1955000 |

- ¿Coincide con la verificación local en SQLite? sí
- **q3_agregacion** - ¿Cuánto se vendió (neto) por categoría de producto y segmento de cliente, y cuál fue el ticket promedio?
- Evidencia: `16_dataapi_q3_agregacion.json` (2026-10-15 20:13:20)

**q3_agregacion** - ¿Cuánto se vendió (neto) por categoría de producto y segmento de cliente, y cuál fue el ticket promedio?

| categoria | segmento | num_pedidos | unidades | ventas_netas | ticket_promedio |
|---|---|---|---|---|---|
| Tecnologia | Corporativo | 39 | 79 | 90797450 | 2328140 |
| Tecnologia | Estandar | 16 | 37 | 50174300 | 3135894 |
| Muebles | Corporativo | 20 | 43 | 38361600 | 1918080 |
| Muebles | Premium | 6 | 14 | 15516550 | 2586092 |
| Muebles | Estandar | 11 | 15 | 14162100 | 1287464 |
| Tecnologia | Premium | 9 | 14 | 7018300 | 779811 |
| Hogar | Corporativo | 9 | 24 | 5367300 | 596367 |
| Hogar | Estandar | 6 | 14 | 3067950 | 511325 |
| Hogar | Premium | 4 | 7 | 1812000 | 453000 |

- ¿Coincide con la verificación local en SQLite? sí
- **q4_top_clientes** - ¿Qué 5 clientes generaron más ventas netas y cuántos pedidos hicieron? (filtro + unión + agregación + HAVING)
- Evidencia: `17_dataapi_q4_top_clientes.json` (2026-10-15 20:13:55)

**q4_top_clientes** - ¿Qué 5 clientes generaron más ventas netas y cuántos pedidos hicieron? (filtro + unión + agregación + HAVING)

| id_cliente | nombre | ciudad | segmento | num_pedidos | ventas_netas |
|---|---|---|---|---|---|
| 16 | Pablo Vargas | Medellin | Corporativo | 7 | 26361050 |
| 4 | Diego Restrepo | Medellin | Corporativo | 10 | 22722450 |
| 15 | Olga Gomez | Envigado | Estandar | 10 | 21965150 |
| 10 | Julian Mejia | Bogota | Corporativo | 7 | 19569500 |
| 14 | Nicolas Gomez | Barranquilla | Estandar | 6 | 18501050 |

- ¿Coincide con la verificación local en SQLite? sí

## Paso 4 - Uso y costos  
_2026-10-15 20:13:55_

- Evidencia: `18_dataapi_uso_serverless.json` (2026-10-15 20:14:30)

**uso_serverless** - Consumo registrado por Redshift Serverless

| rpu_segundos_cobrados | rpu_segundos_computo | rpu_max | almacenamiento_mb |
|---|---|---|---|
| 1200 | 58.0 | 4.0 | 426 |

- Evidencia: `19_precios_api.json` (2026-10-15 20:15:03)

**estimacion_costos** - Precio de referencia 0.375 USD/RPU-h (us-east-1), mínimo 60 s por cobro

| componente | uso | costo_usd |
|---|---|---|
| Cómputo consumido en el taller | 1200 RPU-s | $0.1250 |
| Cómputo 1 hora activa (4 RPU) | 4 RPU-h | $1.50 |
| Cómputo inactivo | 0 RPU | $0.00 (Serverless no cobra sin consultas) |
| Almacenamiento administrado (RMS) | 426 MB | $0.0100/mes |
| Secreto del admin (Secrets Manager) | 1 secreto | $0.40/mes prorrateado (~$0.0005/h) |
| S3 (3 CSV, < 10 KB) | - | < $0.0001/mes |
| Provisionado ra3.large 1 nodo (referencia) | ~$0.54/h | se cobra encendido 24/7 |


## Limpieza - eliminación de recursos y verificación  
_2026-10-15 20:46:35_

- Solicitada la eliminación del workgroup
- Solicitada la eliminación del namespace (sin snapshot final)

**verificacion_eliminacion** 

| recurso | estado |
|---|---|
| Workgroup | no existe (ResourceNotFoundException) |
| Namespace | no existe (ResourceNotFoundException) |
| Secreto admin | no existe (ResourceNotFoundException) |
| Snapshots manuales del namespace | ninguno |
| Rol IAM | no existe |
| Bucket S3 | no existe |

