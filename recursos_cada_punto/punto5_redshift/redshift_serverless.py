"""Punto 5 - Amazon Redshift Serverless + S3 + COPY + Redshift Data API.

Uso (desde la raíz del repositorio):
    uv run python punto5_redshift/redshift_serverless.py todo      # crear, cargar, consultar, costos
    uv run python punto5_redshift/redshift_serverless.py limpiar   # elimina todo y verifica

Pasos individuales: crear | cargar | consultar | inspeccionar | costos | limpiar

- La contraseña del administrador la genera y guarda Redshift en AWS Secrets Manager
  (manageAdminPassword=True). Nadie la escribe ni la ve.
- Todas las sentencias SQL se envían con la API de datos (redshift-data) usando el ARN de
  ese secreto (SecretArn). El programa nunca lee ni imprime la contraseña.
- Redshift lee los CSV de S3 con un rol de IAM asociado al namespace (COPY ... IAM_ROLE).
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from botocore.exceptions import ClientError  # noqa: E402

from comun.precios import REFERENCIA, consultar_seguro  # noqa: E402
from comun.utilidades import (PREFIJO, REGION, Estado, Evidencia, borrar_rol,  # noqa: E402
                              bucket_existe, cliente, crear_bucket, crear_rol_servicio,
                              esperar, id_cuenta, identidad, rol_existe,
                              vaciar_y_borrar_bucket, vpc_por_defecto)
from puntos.punto5_redshift.verificar_local import leer_consultas  # noqa: E402

AQUI = pathlib.Path(__file__).resolve().parent
EV = Evidencia("punto5")
ESTADO = Estado("punto5")

NAMESPACE = f"{PREFIJO}-ns"
WORKGROUP = f"{PREFIJO}-wg"
BASE_DATOS = "tienda"
ADMIN = "admin_taller"
ROL = f"{PREFIJO}-p5-redshift-s3-role"
PREFIJO_S3 = "redshift/datos"
CAPACIDAD_BASE = int(__import__("os").getenv("REDSHIFT_RPU", "4"))  # 4 RPU = mínimo


def nombre_bucket() -> str:
    if not ESTADO.get("bucket"):
        ESTADO["bucket"] = f"{PREFIJO}-p5-{id_cuenta()}-{REGION}"
    return ESTADO["bucket"]


# ------------------------------------------------------------ Redshift Data API
def _valor(campo: dict):
    if campo.get("isNull"):
        return None
    for k in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if k in campo:
            return campo[k]
    return str(campo)


def esperar_sentencia(sid: str) -> dict:
    rd = cliente("redshift-data")
    while True:
        d = rd.describe_statement(Id=sid)
        if d["Status"] in ("FINISHED", "FAILED", "ABORTED"):
            return d
        time.sleep(1)


def sql(sentencias: str | list[str], nombre: str, descripcion: str = "",
        guardar_tabla: bool = True) -> dict:
    """Envía SQL con la API de datos, comprueba que terminó y recupera resultados."""
    rd = cliente("redshift-data")
    comun = {"WorkgroupName": WORKGROUP, "Database": BASE_DATOS,
             "SecretArn": ESTADO["secreto_arn"], "StatementName": f"taller-{nombre}"[:500]}
    if isinstance(sentencias, list):
        sid = rd.batch_execute_statement(Sqls=sentencias, **comun)["Id"]
    else:
        sid = rd.execute_statement(Sql=sentencias, **comun)["Id"]
    d = esperar_sentencia(sid)
    resumen = {"id": sid, "estado": d["Status"], "duracion_ms": d.get("Duration", 0) / 1e6,
               "filas_resultado": d.get("ResultRows"), "error": d.get("Error"),
               "sql": sentencias,
               "subsentencias": [{"sql": s.get("QueryString"), "estado": s.get("Status"),
                                  "duracion_ms": s.get("Duration", 0) / 1e6,
                                  "error": s.get("Error")} for s in d.get("SubStatements", [])]}
    EV.paso(f"dataapi_{nombre}", resumen, mostrar=False)
    print(f"  [data api] {nombre}: {d['Status']} en {resumen['duracion_ms']:.0f} ms")
    if d["Status"] != "FINISHED":
        raise RuntimeError(f"La sentencia {nombre} terminó en {d['Status']}: {d.get('Error')}")
    columnas, filas = [], []
    if d.get("HasResultSet"):
        token = None
        while True:
            kw = {"Id": sid}
            if token:
                kw["NextToken"] = token
            r = rd.get_statement_result(**kw)
            if not columnas:
                columnas = [c["name"] for c in r["ColumnMetadata"]]
            filas += [[_valor(c) for c in reg] for reg in r["Records"]]
            token = r.get("NextToken")
            if not token:
                break
        if guardar_tabla:
            EV.tabla(nombre, columnas, filas, descripcion)
    resumen.update(columnas=columnas, filas=filas)
    return resumen


def separar_sql(texto: str) -> list[str]:
    lineas = [ln for ln in texto.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lineas).split(";") if s.strip()]


# --------------------------------------------------------------------- pasos
def crear() -> None:
    EV.titulo("Paso 1 - Despliegue de Redshift Serverless")
    EV.paso("identidad_usada", identidad())
    bucket = nombre_bucket()
    crear_bucket(bucket)
    EV.nota(f"Bucket privado: s3://{bucket}")

    politica = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["s3:GetObject"],
         "Resource": f"arn:aws:s3:::{bucket}/{PREFIJO_S3}/*"},
        {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
         "Resource": f"arn:aws:s3:::{bucket}"}]}
    try:
        rol_arn = crear_rol_servicio(ROL, ["redshift.amazonaws.com",
                                           "redshift-serverless.amazonaws.com"], [], politica,
                                     "Permite a Redshift leer los CSV del taller en S3 (COPY)")
    except ClientError as e:
        if "MalformedPolicyDocument" not in str(e):
            raise
        rol_arn = crear_rol_servicio(ROL, ["redshift.amazonaws.com"], [], politica)
    ESTADO["rol_arn"] = rol_arn
    iam = cliente("iam")
    EV.paso("rol_copy_confianza", iam.get_role(RoleName=ROL)["Role"])
    EV.paso("rol_copy_permisos", iam.get_role_policy(RoleName=ROL, PolicyName=f"{ROL}-inline"))

    rs = cliente("redshift-serverless")
    try:
        ns = rs.create_namespace(
            namespaceName=NAMESPACE, dbName=BASE_DATOS, adminUsername=ADMIN,
            manageAdminPassword=True,          # contraseña administrada en Secrets Manager
            iamRoles=[rol_arn], defaultIamRoleArn=rol_arn,
            logExports=[], tags=[{"key": "proyecto", "value": PREFIJO}])["namespace"]
    except rs.exceptions.ConflictException:
        ns = rs.get_namespace(namespaceName=NAMESPACE)["namespace"]
    esperar(lambda: rs.get_namespace(namespaceName=NAMESPACE)["namespace"]["status"] == "AVAILABLE",
            "namespace AVAILABLE", 10, 900)
    ns = rs.get_namespace(namespaceName=NAMESPACE)["namespace"]
    ESTADO["secreto_arn"] = ns["adminPasswordSecretArn"]
    EV.paso("namespace", ns)
    EV.nota(f"Secreto del administrador (administrado por Redshift): {ns['adminPasswordSecretArn']}")
    sm = cliente("secretsmanager").describe_secret(SecretId=ns["adminPasswordSecretArn"])
    EV.paso("secreto_admin_metadatos", sm)  # solo metadatos, nunca el valor

    _, subredes = vpc_por_defecto()
    sg = cliente("ec2").describe_security_groups(Filters=[
        {"Name": "vpc-id", "Values": [subredes[0]["VpcId"]]},
        {"Name": "group-name", "Values": ["default"]}])["SecurityGroups"][0]["GroupId"]
    base = CAPACIDAD_BASE
    try:
        try:
            rs.create_workgroup(
                workgroupName=WORKGROUP, namespaceName=NAMESPACE, baseCapacity=base,
                subnetIds=[s["SubnetId"] for s in subredes], securityGroupIds=[sg],
                publiclyAccessible=False, enhancedVpcRouting=False,
                tags=[{"key": "proyecto", "value": PREFIJO}])
        except rs.exceptions.ValidationException as e:
            if base != 4:
                raise
            EV.nota(f"4 RPU no disponible ({e}); se usa 8 RPU")
            base = 8
            rs.create_workgroup(
                workgroupName=WORKGROUP, namespaceName=NAMESPACE, baseCapacity=base,
                subnetIds=[s["SubnetId"] for s in subredes], securityGroupIds=[sg],
                publiclyAccessible=False, tags=[{"key": "proyecto", "value": PREFIJO}])
    except rs.exceptions.ConflictException:
        pass
    esperar(lambda: rs.get_workgroup(workgroupName=WORKGROUP)["workgroup"]["status"] == "AVAILABLE",
            "workgroup AVAILABLE", 15, 1800)
    wg = rs.get_workgroup(workgroupName=WORKGROUP)["workgroup"]
    EV.paso("workgroup", wg)
    EV.nota(f"Workgroup {WORKGROUP}: capacidad base {wg.get('baseCapacity')} RPU, "
            f"acceso público={wg.get('publiclyAccessible')}, endpoint={wg['endpoint']['address']}")
    try:
        lim = rs.create_usage_limit(resourceArn=wg["workgroupArn"], usageType="serverless-compute",
                                    amount=4, period="daily", breachAction="log")["usageLimit"]
        EV.paso("limite_uso", lim)
        EV.nota("Límite de uso: 4 RPU-hora/día (alerta en log) como control de costos")
    except ClientError as e:
        EV.nota(f"No se creó el límite de uso: {e}")


def cargar() -> None:
    EV.titulo("Paso 2 - Subida a S3, creación de tablas y COPY")
    s3, bucket = cliente("s3"), nombre_bucket()
    for t in ("clientes", "productos", "pedidos"):
        s3.upload_file(str(AQUI / "datos" / f"{t}.csv"), bucket, f"{PREFIJO_S3}/{t}.csv")
    EV.paso("s3_objetos", s3.list_objects_v2(Bucket=bucket, Prefix=PREFIJO_S3))
    EV.nota(f"CSV subidos a s3://{bucket}/{PREFIJO_S3}/")

    ddl = separar_sql((AQUI / "sql" / "01_crear_tablas.sql").read_text(encoding="utf-8"))
    sql(ddl, "crear_tablas")
    plantilla = (AQUI / "sql" / "02_copy.sql").read_text(encoding="utf-8")
    copys = separar_sql(plantilla.format(bucket=bucket, prefijo=PREFIJO_S3,
                                         rol=ESTADO["rol_arn"], region=REGION))
    try:
        sql(copys, "copy_desde_s3")
    except RuntimeError:
        sql("SELECT * FROM sys_load_error_detail ORDER BY start_time DESC LIMIT 20",
            "errores_de_carga", "Errores del COPY")
        raise
    sql("""SELECT 'clientes' AS tabla, COUNT(*) AS filas FROM clientes
UNION ALL SELECT 'productos', COUNT(*) FROM productos
UNION ALL SELECT 'pedidos', COUNT(*) FROM pedidos ORDER BY 1""",
        "conteo_filas_cargadas", "Filas cargadas por COPY (esperado: 20, 10, 120)")
    try:
        sql("""SELECT query_id, table_name, file_format, loaded_rows, loaded_bytes, duration,
       status FROM sys_load_history ORDER BY start_time DESC LIMIT 3""",
            "historial_copy", "Historial de cargas COPY")
    except RuntimeError as e:
        EV.nota(f"No se pudo leer sys_load_history: {e}")


def inspeccionar() -> None:
    EV.titulo("Inspección de componentes (tablas, distribución, ordenamiento)")
    try:
        sql("""SELECT "table" AS tabla, diststyle, sortkey1, tbl_rows, size AS bloques_1mb
FROM svv_table_info WHERE "schema" = 'public' ORDER BY 1""",
            "svv_table_info", "Estilo de distribución y llave de ordenamiento de cada tabla")
    except RuntimeError as e:
        EV.nota(f"No se pudo leer svv_table_info: {e}")


def _normalizar(v):
    try:
        return round(float(v), 0)
    except (TypeError, ValueError):
        return str(v)


def consultar() -> None:
    EV.titulo("Paso 3 - Consultas (filtro, unión, agregación)")
    for c in leer_consultas():
        EV.nota(f"**{c['nombre']}** - {c['pregunta']}")
        r = sql(c["sql"], c["nombre"], c["pregunta"])
        esperado_csv = AQUI / "resultados_esperados" / f"{c['nombre']}.csv"
        if esperado_csv.exists():
            import csv
            with esperado_csv.open(encoding="utf-8") as f:
                esperado = list(csv.reader(f))[1:]
            igual = [[_normalizar(v) for v in fila] for fila in r["filas"]] == \
                    [[_normalizar(v) for v in fila] for fila in esperado]
            EV.nota(f"¿Coincide con la verificación local en SQLite? {'sí' if igual else 'NO'}")


def costos() -> None:
    EV.titulo("Paso 4 - Uso y costos")
    try:
        r = sql("""SELECT SUM(charged_seconds) AS rpu_segundos_cobrados,
       SUM(compute_seconds) AS rpu_segundos_computo,
       MAX(compute_capacity) AS rpu_max, MAX(data_storage) AS almacenamiento_mb
FROM sys_serverless_usage""", "uso_serverless", "Consumo registrado por Redshift Serverless")
        rpu_s = float(r["filas"][0][0] or 0)
        alm_mb = float(r["filas"][0][3] or 0)
    except RuntimeError:
        rpu_s, alm_mb = 0.0, 0.0
    precios = {"redshift_serverless": consultar_seguro("AmazonRedshift", ["serverless"]),
               "secrets_manager": consultar_seguro("AWSSecretsManager", ["secret"])}
    EV.paso("precios_api", precios)
    p = REFERENCIA["redshift_rpu_hora"]
    filas = [
        ["Cómputo consumido en el taller", f"{rpu_s:.0f} RPU-s", f"${rpu_s / 3600 * p:.4f}"],
        ["Cómputo 1 hora activa (4 RPU)", "4 RPU-h", f"${4 * p:.2f}"],
        ["Cómputo inactivo", "0 RPU", "$0.00 (Serverless no cobra sin consultas)"],
        ["Almacenamiento administrado (RMS)", f"{alm_mb:.0f} MB",
         f"${alm_mb / 1024 * REFERENCIA['redshift_rms_gb_mes']:.4f}/mes"],
        ["Secreto del admin (Secrets Manager)", "1 secreto",
         f"${REFERENCIA['secrets_mes']:.2f}/mes prorrateado (~${REFERENCIA['secrets_mes'] / 730:.4f}/h)"],
        ["S3 (3 CSV, < 10 KB)", "-", "< $0.0001/mes"],
        ["Provisionado ra3.large 1 nodo (referencia)", "~$0.54/h", "se cobra encendido 24/7"],
    ]
    EV.tabla("estimacion_costos", ["componente", "uso", "costo_usd"], filas,
             f"Precio de referencia {p} USD/RPU-h ({REGION}), mínimo 60 s por cobro")


def limpiar() -> None:
    EV.titulo("Limpieza - eliminación de recursos y verificación")
    rs = cliente("redshift-serverless")
    secreto = ESTADO.get("secreto_arn")
    try:
        rs.delete_workgroup(workgroupName=WORKGROUP)
        EV.nota("Solicitada la eliminación del workgroup")

        def wg_borrado():
            try:
                rs.get_workgroup(workgroupName=WORKGROUP)
                return False
            except rs.exceptions.ResourceNotFoundException:
                return True
        esperar(wg_borrado, "workgroup eliminado", 15, 1800)
    except rs.exceptions.ResourceNotFoundException:
        EV.nota("El workgroup no existía")
    try:
        rs.delete_namespace(namespaceName=NAMESPACE)   # sin snapshot final
        EV.nota("Solicitada la eliminación del namespace (sin snapshot final)")

        def ns_borrado():
            try:
                rs.get_namespace(namespaceName=NAMESPACE)
                return False
            except rs.exceptions.ResourceNotFoundException:
                return True
        esperar(ns_borrado, "namespace eliminado", 15, 1800)
    except rs.exceptions.ResourceNotFoundException:
        EV.nota("El namespace no existía")
    borrar_rol(ROL)
    vaciar_y_borrar_bucket(nombre_bucket())

    def existe(fn):
        try:
            fn()
            return "SIGUE EXISTIENDO"
        except Exception as e:
            return f"no existe ({type(e).__name__})"

    estado_secreto = "no aplica"
    if secreto:
        try:
            d = cliente("secretsmanager").describe_secret(SecretId=secreto)
            estado_secreto = (f"programado para borrado el {d['DeletedDate']}"
                              if d.get("DeletedDate") else "SIGUE EXISTIENDO")
        except ClientError as e:
            estado_secreto = f"no existe ({e.response['Error']['Code']})"
    snaps = rs.list_snapshots().get("snapshots", [])
    snaps = [s["snapshotName"] for s in snaps if s.get("namespaceName") == NAMESPACE]
    verif = [
        ["Workgroup", existe(lambda: rs.get_workgroup(workgroupName=WORKGROUP))],
        ["Namespace", existe(lambda: rs.get_namespace(namespaceName=NAMESPACE))],
        ["Secreto admin", estado_secreto],
        ["Snapshots manuales del namespace", ", ".join(snaps) or "ninguno"],
        ["Rol IAM", "SIGUE EXISTIENDO" if rol_existe(ROL) else "no existe"],
        ["Bucket S3", "SIGUE EXISTIENDO" if bucket_existe(nombre_bucket()) else "no existe"],
    ]
    EV.tabla("verificacion_eliminacion", ["recurso", "estado"], verif)
    ESTADO.borrar()


PASOS = {"crear": crear, "cargar": cargar, "inspeccionar": inspeccionar, "consultar": consultar,
         "costos": costos, "limpiar": limpiar}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("paso", choices=list(PASOS) + ["todo"])
    a = ap.parse_args()
    print(f"Región: {REGION} | prefijo: {PREFIJO}")
    if a.paso == "todo":
        for p in ("crear", "cargar", "inspeccionar", "consultar", "costos"):
            PASOS[p]()
        print("\nListo. Revise evidencias/punto5/. Puede abrir Query Editor v2 con el secreto "
              "del admin. Luego: uv run python punto5_redshift/redshift_serverless.py limpiar")
    else:
        PASOS[a.paso]()
