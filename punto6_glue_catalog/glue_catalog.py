"""Punto 6 - AWS Glue Data Catalog + crawler + Athena.

Uso (desde la raíz del repositorio):
    uv run python punto6_glue_catalog/glue_catalog.py todo       # todos los pasos
    uv run python punto6_glue_catalog/glue_catalog.py limpiar    # elimina todo y verifica

Pasos individuales: crear | crawler | corregir | consultar | agregar | manual | costos

Flujo:
 1. crear     -> bucket S3 privado, sube ventas_2026-09.csv a s3://.../ventas/mes=2026-09/,
                 base de datos de Glue, rol IAM del crawler, workgroup de Athena.
 2. crawler   -> crea y ejecuta el crawler, guarda el esquema inferido.
 3. corregir  -> compara el esquema inferido con el esperado y corrige los tipos
                 (tabla y particiones). Muestra el antes/después en Athena.
 4. consultar -> consultas Athena con filtro y con agrupación.
 5. agregar   -> sube 10 registros nuevos (mes=2026-10), vuelve a ejecutar el crawler y
                 verifica la nueva partición, que el esquema corregido se conserva y el conteo.
 6. manual    -> crea la misma tabla a mano con DDL de Athena para comparar con el crawler.
 7. costos    -> estima el costo con los datos escaneados reales y la API de precios.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from comun.precios import REFERENCIA, consultar_seguro  # noqa: E402
from comun.utilidades import (PREFIJO, REGION, Estado, Evidencia, borrar_rol,  # noqa: E402
                              bucket_existe, cliente, crear_bucket, crear_rol_servicio,
                              esperar, id_cuenta, identidad, rol_existe,
                              vaciar_y_borrar_bucket)

AQUI = pathlib.Path(__file__).resolve().parent
EV = Evidencia("punto6")
ESTADO = Estado("punto6")

BASE_DATOS = "taller_ventas_db"
CRAWLER = f"{PREFIJO}-p6-crawler"
ROL = f"{PREFIJO}-p6-glue-crawler-role"
WORKGROUP = f"{PREFIJO}-p6-wg"
TABLA_MANUAL = "ventas_manual"

# Esquema correcto que debería tener la tabla
ESQUEMA_ESPERADO = {
    "id_venta": "bigint",
    "fecha": "date",
    "ciudad": "string",
    "codigo_postal": "string",       # tiene ceros a la izquierda: NO es un número
    "producto": "string",
    "categoria": "string",
    "cantidad": "int",
    "precio_unitario": "decimal(12,2)",  # dinero: decimal exacto en vez de double
    "cliente_vip": "boolean",
}


def nombre_bucket() -> str:
    if not ESTADO.get("bucket"):
        ESTADO["bucket"] = f"{PREFIJO}-p6-{id_cuenta()}-{REGION}"
    return ESTADO["bucket"]


# --------------------------------------------------------------------- Athena
def athena(sql: str, nombre: str | None = None, descripcion: str = "") -> dict:
    """Ejecuta SQL en Athena, espera, guarda resultados y estadísticas como evidencia."""
    ath = cliente("athena")
    qid = ath.start_query_execution(
        QueryString=sql, WorkGroup=WORKGROUP,
        QueryExecutionContext={"Database": BASE_DATOS})["QueryExecutionId"]
    while True:
        ex = ath.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        estado = ex["Status"]["State"]
        if estado in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1.5)
    stats = ex.get("Statistics", {})
    info = {"sql": sql, "estado": estado, "query_id": qid,
            "bytes_escaneados": stats.get("DataScannedInBytes", 0),
            "tiempo_motor_ms": stats.get("EngineExecutionTimeInMillis"),
            "motivo": ex["Status"].get("StateChangeReason")}
    if estado != "SUCCEEDED":
        EV.paso(f"athena_error_{nombre or 'consulta'}", info)
        raise RuntimeError(f"Athena {estado}: {info['motivo']}")
    columnas, filas, token = [], [], None
    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kw["NextToken"] = token
        res = ath.get_query_results(**kw)
        if not columnas:
            columnas = [c["Name"] for c in res["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
        for fila in res["ResultSet"]["Rows"]:
            filas.append([d.get("VarCharValue") for d in fila["Data"]])
        token = res.get("NextToken")
        if not token:
            break
    if filas and filas[0] == columnas:  # en SELECT la primera fila es el encabezado
        filas = filas[1:]
    info.update(columnas=columnas, filas=len(filas))
    if nombre:
        EV.paso(f"athena_{nombre}", info, mostrar=False)
        EV.tabla(nombre, columnas, filas,
                 f"{descripcion} (escaneado: {info['bytes_escaneados']} bytes)")
    consultas = ESTADO.get("consultas_athena", [])
    consultas.append({"nombre": nombre or sql[:40], "bytes": info["bytes_escaneados"]})
    ESTADO["consultas_athena"] = consultas
    info["datos"] = filas
    return info


# --------------------------------------------------------------------- pasos
def crear() -> None:
    EV.titulo("Paso 1 - Recursos base (S3, Glue Database, rol del crawler, workgroup Athena)")
    EV.paso("identidad_usada", identidad())
    bucket = nombre_bucket()
    crear_bucket(bucket)
    EV.nota(f"Bucket privado creado: s3://{bucket} (Block Public Access activado)")

    s3 = cliente("s3")
    archivo = AQUI / "datos" / "ventas_2026-09.csv"
    clave = "ventas/mes=2026-09/ventas_2026-09.csv"
    s3.upload_file(str(archivo), bucket, clave)
    EV.nota(f"Subido {archivo.name} (25 registros) a s3://{bucket}/{clave}")
    EV.paso("s3_objetos", s3.list_objects_v2(Bucket=bucket, Prefix="ventas/"))

    glue = cliente("glue")
    try:
        glue.create_database(DatabaseInput={
            "Name": BASE_DATOS,
            "Description": "Taller Ingeniería de Datos - punto 6 (ventas)"})
    except glue.exceptions.AlreadyExistsException:
        pass
    EV.paso("glue_database", glue.get_database(Name=BASE_DATOS))

    politica = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject"],
             "Resource": f"arn:aws:s3:::{bucket}/ventas/*"},
            {"Effect": "Allow", "Action": ["s3:ListBucket"],
             "Resource": f"arn:aws:s3:::{bucket}"},
        ],
    }
    arn = crear_rol_servicio(
        ROL, ["glue.amazonaws.com"],
        ["arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"], politica,
        "Rol del crawler de Glue del taller (solo lectura de s3://bucket/ventas/)")
    ESTADO["rol_arn"] = arn
    EV.texto("politica_rol_crawler.json", json.dumps(politica, indent=2))
    EV.nota(f"Rol del crawler: {arn} (AWSGlueServiceRole + lectura del prefijo ventas/)")

    ath = cliente("athena")
    try:
        ath.create_work_group(
            Name=WORKGROUP,
            Description="Workgroup del taller: resultados en S3 y límite de 10 MB por consulta",
            Configuration={
                "ResultConfiguration": {"OutputLocation": f"s3://{bucket}/athena-resultados/"},
                "EnforceWorkGroupConfiguration": True,
                "PublishCloudWatchMetricsEnabled": False,
                "BytesScannedCutoffPerQuery": 10 * 1024 * 1024,  # control de costos
            })
    except ath.exceptions.InvalidRequestException as e:
        if "already" not in str(e).lower():
            raise
    EV.paso("athena_workgroup", ath.get_work_group(WorkGroup=WORKGROUP))


def ejecutar_crawler(etiqueta: str) -> dict:
    glue = cliente("glue")
    glue.start_crawler(Name=CRAWLER)
    time.sleep(10)

    def listo():
        c = glue.get_crawler(Name=CRAWLER)["Crawler"]
        return c if c["State"] == "READY" else None

    c = esperar(listo, f"fin del crawler ({etiqueta})", intervalo=15, maximo=1200)
    EV.paso(f"crawler_ejecucion_{etiqueta}", c.get("LastCrawl", {}))
    metricas = glue.get_crawler_metrics(CrawlerNameList=[CRAWLER])["CrawlerMetricsList"]
    EV.paso(f"crawler_metricas_{etiqueta}", metricas)
    if c.get("LastCrawl", {}).get("Status") != "SUCCEEDED":
        raise RuntimeError(f"El crawler terminó con estado {c.get('LastCrawl')}")
    return c


def nombre_tabla() -> str:
    tablas = [t["Name"] for t in cliente("glue").get_tables(DatabaseName=BASE_DATOS)["TableList"]
              if t["Name"] != TABLA_MANUAL]
    if not tablas:
        raise RuntimeError("El crawler no creó tablas; revise el log del crawler en CloudWatch")
    ESTADO["tabla"] = tablas[0]
    return tablas[0]


def crawler() -> None:
    EV.titulo("Paso 2 - Crawler: descubrimiento del esquema")
    glue = cliente("glue")
    config = {
        "Version": 1.0,
        # Las particiones nuevas heredan el esquema (corregido) de la tabla
        "CrawlerOutput": {"Partitions": {"AddOrUpdateBehavior": "InheritFromTable"}},
    }
    try:
        glue.create_crawler(
            Name=CRAWLER, Role=ESTADO["rol_arn"], DatabaseName=BASE_DATOS,
            Description="Descubre s3://bucket/ventas/ (CSV particionado por mes)",
            Targets={"S3Targets": [{"Path": f"s3://{nombre_bucket()}/ventas/"}]},
            # LOG = no sobrescribir el esquema que corregimos manualmente en re-ejecuciones
            SchemaChangePolicy={"UpdateBehavior": "LOG", "DeleteBehavior": "LOG"},
            RecrawlPolicy={"RecrawlBehavior": "CRAWL_EVERYTHING"},
            Configuration=json.dumps(config))
    except glue.exceptions.AlreadyExistsException:
        pass
    EV.paso("crawler_configuracion", glue.get_crawler(Name=CRAWLER)["Crawler"])
    ejecutar_crawler("inicial")
    tabla = glue.get_table(DatabaseName=BASE_DATOS, Name=nombre_tabla())["Table"]
    EV.paso("esquema_inferido_tabla", tabla)
    cols = tabla["StorageDescriptor"]["Columns"]
    EV.tabla("esquema_inferido", ["columna", "tipo_inferido", "tipo_esperado", "correcto"],
             [[c["Name"], c["Type"], ESQUEMA_ESPERADO.get(c["Name"], "?"),
               "sí" if c["Type"] == ESQUEMA_ESPERADO.get(c["Name"]) else "NO"] for c in cols],
             "Esquema que infirió el crawler vs el esperado")
    EV.tabla("particiones_inferidas", ["clave", "tipo"],
             [[p["Name"], p["Type"]] for p in tabla.get("PartitionKeys", [])])
    EV.nota(f"Clasificación: {tabla.get('Parameters', {}).get('classification')}, "
            f"SerDe: {tabla['StorageDescriptor']['SerdeInfo'].get('SerializationLibrary')}, "
            f"skip.header.line.count={tabla.get('Parameters', {}).get('skip.header.line.count')}")


_CAMPOS_TABLA = ("Name", "Description", "Owner", "Retention", "StorageDescriptor",
                 "PartitionKeys", "TableType", "Parameters")


def corregir() -> None:
    EV.titulo("Paso 3 - Revisión y corrección del esquema")
    glue = cliente("glue")
    nombre = nombre_tabla()
    antes = athena(f'SELECT DISTINCT ciudad, codigo_postal FROM "{nombre}" ORDER BY ciudad',
                   "antes_correccion_codigos", "Códigos postales con el tipo inferido")
    tabla = glue.get_table(DatabaseName=BASE_DATOS, Name=nombre)["Table"]
    cambios = []
    for col in tabla["StorageDescriptor"]["Columns"]:
        esperado = ESQUEMA_ESPERADO.get(col["Name"])
        if esperado and col["Type"] != esperado:
            cambios.append([col["Name"], col["Type"], esperado])
            col["Type"] = esperado
    tabla.setdefault("Parameters", {})["comentario_taller"] = "tipos corregidos manualmente"
    entrada = {k: tabla[k] for k in _CAMPOS_TABLA if k in tabla}
    glue.update_table(DatabaseName=BASE_DATOS, TableInput=entrada)
    EV.tabla("correcciones_esquema", ["columna", "tipo_inferido", "tipo_corregido"], cambios,
             "Cambios aplicados con glue.update_table")

    # Las particiones guardan su propia copia del esquema: también hay que corregirlas,
    # si no Athena lanza HIVE_PARTITION_SCHEMA_MISMATCH.
    columnas = tabla["StorageDescriptor"]["Columns"]
    for p in glue.get_partitions(DatabaseName=BASE_DATOS, TableName=nombre)["Partitions"]:
        sd = p["StorageDescriptor"]
        sd["Columns"] = columnas
        glue.update_partition(DatabaseName=BASE_DATOS, TableName=nombre,
                              PartitionValueList=p["Values"],
                              PartitionInput={"Values": p["Values"], "StorageDescriptor": sd,
                                              "Parameters": p.get("Parameters", {})})
        EV.nota(f"Partición {p['Values']} actualizada con el esquema corregido")
    EV.paso("esquema_corregido_tabla", glue.get_table(DatabaseName=BASE_DATOS, Name=nombre))
    despues = athena(f'SELECT DISTINCT ciudad, codigo_postal FROM "{nombre}" ORDER BY ciudad',
                     "despues_correccion_codigos", "Códigos postales con tipo string")
    EV.nota(f"Antes: {antes['datos']} | Después: {despues['datos']}")
    athena(f'SELECT typeof(fecha) t_fecha, typeof(precio_unitario) t_precio, '
           f'typeof(codigo_postal) t_cp, typeof(cantidad) t_cant FROM "{nombre}" LIMIT 1',
           "tipos_en_athena", "Tipos que ve Athena tras la corrección")


def consultar() -> None:
    EV.titulo("Paso 4 - Consultas en Athena")
    t = nombre_tabla()
    athena(f"""SELECT id_venta, fecha, ciudad, producto, cantidad, precio_unitario
FROM "{t}"
WHERE categoria = 'Tecnologia' AND cantidad >= 3
ORDER BY fecha""", "consulta_filtro",
           "¿Qué ventas de Tecnología tuvieron 3 o más unidades?")
    athena(f"""SELECT categoria,
       COUNT(*)                                  AS num_ventas,
       SUM(cantidad)                             AS unidades,
       CAST(SUM(cantidad * precio_unitario) AS decimal(14,2)) AS total_ventas,
       CAST(AVG(cantidad * precio_unitario) AS decimal(14,2)) AS ticket_promedio
FROM "{t}"
GROUP BY categoria
ORDER BY total_ventas DESC""", "consulta_agrupacion",
           "Ventas totales, unidades y ticket promedio por categoría")
    athena(f"""SELECT ciudad, cliente_vip, COUNT(*) AS num_ventas,
       CAST(SUM(cantidad * precio_unitario) AS decimal(14,2)) AS total
FROM "{t}" GROUP BY ciudad, cliente_vip ORDER BY ciudad, cliente_vip""",
           "consulta_agrupacion_ciudad", "Ventas por ciudad y tipo de cliente")


def agregar() -> None:
    EV.titulo("Paso 5 - Agregar registros y actualizar el catálogo")
    glue, t = cliente("glue"), nombre_tabla()
    antes = athena(f'SELECT mes, COUNT(*) AS registros FROM "{t}" GROUP BY mes ORDER BY mes',
                   "conteo_antes_de_agregar", "Registros por partición antes")
    parts_antes = glue.get_partitions(DatabaseName=BASE_DATOS, TableName=t)["Partitions"]
    clave = "ventas/mes=2026-10/ventas_2026-10.csv"
    cliente("s3").upload_file(str(AQUI / "datos" / "ventas_2026-10.csv"), nombre_bucket(), clave)
    EV.nota(f"Subido ventas_2026-10.csv (10 registros nuevos) a s3://{nombre_bucket()}/{clave}")

    ejecutar_crawler("tras_agregar")
    parts = glue.get_partitions(DatabaseName=BASE_DATOS, TableName=t)["Partitions"]
    if len(parts) == len(parts_antes):
        EV.nota("El crawler no registró la partición nueva; se usa MSCK REPAIR TABLE")
        athena(f'MSCK REPAIR TABLE "{t}"')
        parts = glue.get_partitions(DatabaseName=BASE_DATOS, TableName=t)["Partitions"]
    EV.tabla("particiones_en_catalogo", ["valores", "ubicacion", "columnas_iguales_a_tabla"],
             [[p["Values"], p["StorageDescriptor"]["Location"],
               {c["Name"]: c["Type"] for c in p["StorageDescriptor"]["Columns"]} == ESQUEMA_ESPERADO]
              for p in parts], "Particiones registradas tras volver a ejecutar el crawler")
    tabla = glue.get_table(DatabaseName=BASE_DATOS, Name=t)["Table"]
    conservado = {c["Name"]: c["Type"] for c in tabla["StorageDescriptor"]["Columns"]} == ESQUEMA_ESPERADO
    EV.nota(f"¿El crawler conservó el esquema corregido? {'sí' if conservado else 'NO'} "
            "(SchemaChangePolicy.UpdateBehavior=LOG)")
    despues = athena(f'SELECT mes, COUNT(*) AS registros FROM "{t}" GROUP BY mes ORDER BY mes',
                     "conteo_despues_de_agregar", "Registros por partición después")
    total_antes = sum(int(r[1]) for r in antes["datos"])
    total_despues = sum(int(r[1]) for r in despues["datos"])
    EV.nota(f"Total de registros: {total_antes} -> {total_despues}")
    # Las consultas por partición escanean menos datos
    athena(f"""SELECT COUNT(*) AS ventas_octubre FROM "{t}" WHERE mes = '2026-10'""",
           "consulta_poda_particion", "Solo lee la partición 2026-10 (menos bytes escaneados)")


def manual() -> None:
    EV.titulo("Paso 6 - Tabla creada manualmente (DDL) para comparar con el crawler")
    ddl = f"""CREATE EXTERNAL TABLE IF NOT EXISTS {TABLA_MANUAL} (
  id_venta bigint,
  fecha date,
  ciudad string,
  codigo_postal string,
  producto string,
  categoria string,
  cantidad int,
  precio_unitario decimal(12,2),
  cliente_vip boolean
)
PARTITIONED BY (mes string)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://{nombre_bucket()}/ventas/'
TBLPROPERTIES ('skip.header.line.count'='1', 'classification'='csv')"""
    EV.texto("ddl_tabla_manual.sql", ddl + ";\n")
    athena(ddl)
    athena(f"MSCK REPAIR TABLE {TABLA_MANUAL}")  # registra las particiones existentes
    EV.paso("tabla_manual", cliente("glue").get_table(DatabaseName=BASE_DATOS, Name=TABLA_MANUAL))
    athena(f"""SELECT categoria, COUNT(*) AS num_ventas,
       CAST(SUM(cantidad * precio_unitario) AS decimal(14,2)) AS total_ventas
FROM {TABLA_MANUAL} GROUP BY categoria ORDER BY total_ventas DESC""",
           "consulta_tabla_manual", "Misma agrupación sobre la tabla manual")


def costos() -> None:
    EV.titulo("Paso 7 - Estimación de costos")
    precios = {
        "glue_crawler": consultar_seguro("AWSGlue", ["crawler"]),
        "glue_catalogo": consultar_seguro("AWSGlue", ["catalog"]),
        "athena": consultar_seguro("AmazonAthena", ["terabyte"]),
    }
    EV.paso("precios_api", precios)
    glue = cliente("glue")
    metr = glue.get_crawler_metrics(CrawlerNameList=[CRAWLER])["CrawlerMetricsList"]
    consultas = ESTADO.get("consultas_athena", [])
    min_bytes = 10 * 1024 * 1024
    facturable = sum(max(c["bytes"], min_bytes) for c in consultas if c["bytes"] > 0)
    real = sum(c["bytes"] for c in consultas)
    costo_athena = facturable / 1024 ** 4 * REFERENCIA["athena_tb"]
    # Un crawler se cobra por DPU-hora con mínimo de 10 minutos por ejecución.
    ejecuciones = 2
    dpu_supuestas = 2
    costo_crawler = ejecuciones * dpu_supuestas * (10 / 60) * REFERENCIA["glue_dpu_hora"]
    tam = sum(p.stat().st_size for p in (AQUI / "datos").glob("*.csv"))
    filas = [
        ["Athena (bytes reales escaneados)", f"{real} B en {len(consultas)} consultas", "-"],
        ["Athena (facturable, mín. 10 MB/consulta con datos)", f"{facturable / 1024 ** 2:.0f} MB",
         f"${costo_athena:.4f}"],
        ["Crawler (2 ejecuciones x 10 min mín. x ~2 DPU)", f"{REFERENCIA['glue_dpu_hora']} USD/DPU-h",
         f"${costo_crawler:.4f}"],
        ["Glue Data Catalog (2 tablas, 2-4 particiones)", "< 1 millón de objetos", "$0.00 (capa gratuita)"],
        ["S3 almacenamiento (CSV + resultados Athena)", f"{tam} B", "< $0.0001/mes"],
        ["S3 solicitudes PUT/GET", "decenas", "< $0.001"],
    ]
    EV.tabla("estimacion_costos", ["componente", "uso", "costo_estimado_usd"], filas,
             "Precios de referencia us-east-1; ver precios_api para los valores de la API")
    EV.paso("crawler_metricas_finales", metr)


def limpiar() -> None:
    EV.titulo("Limpieza - eliminación de recursos y verificación")
    glue, ath = cliente("glue"), cliente("athena")
    bucket = nombre_bucket()
    pasos = [
        ("workgroup Athena", lambda: ath.delete_work_group(WorkGroup=WORKGROUP,
                                                           RecursiveDeleteOption=True)),
        ("crawler", lambda: glue.delete_crawler(Name=CRAWLER)),
        ("base de datos Glue (y sus tablas)", lambda: glue.delete_database(Name=BASE_DATOS)),
        ("rol IAM", lambda: borrar_rol(ROL)),
        ("bucket S3", lambda: vaciar_y_borrar_bucket(bucket)),
    ]
    for nombre, fn in pasos:
        try:
            fn()
            EV.nota(f"Eliminado: {nombre}")
        except Exception as e:
            EV.nota(f"{nombre}: {type(e).__name__} ({e})")
    time.sleep(5)

    def existe(fn):
        try:
            fn()
            return "SIGUE EXISTIENDO"
        except Exception as e:
            return f"no existe ({type(e).__name__})"

    verif = [
        ["Workgroup Athena", existe(lambda: ath.get_work_group(WorkGroup=WORKGROUP))],
        ["Crawler", existe(lambda: glue.get_crawler(Name=CRAWLER))],
        ["Base de datos Glue", existe(lambda: glue.get_database(Name=BASE_DATOS))],
        ["Rol IAM", "SIGUE EXISTIENDO" if rol_existe(ROL) else "no existe"],
        ["Bucket S3", "SIGUE EXISTIENDO" if bucket_existe(bucket) else "no existe"],
    ]
    EV.tabla("verificacion_eliminacion", ["recurso", "estado"], verif,
             "Comprobación posterior a la eliminación")
    ESTADO.borrar()


PASOS = {"crear": crear, "crawler": crawler, "corregir": corregir, "consultar": consultar,
         "agregar": agregar, "manual": manual, "costos": costos, "limpiar": limpiar}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("paso", choices=list(PASOS) + ["todo"])
    a = ap.parse_args()
    print(f"Región: {REGION} | prefijo: {PREFIJO}")
    if a.paso == "todo":
        for p in ("crear", "crawler", "corregir", "consultar", "agregar", "manual", "costos"):
            PASOS[p]()
        print("\nListo. Revise evidencias/punto6/ y luego ejecute: "
              "uv run python punto6_glue_catalog/glue_catalog.py limpiar")
    else:
        PASOS[a.paso]()
