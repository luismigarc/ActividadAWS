"""Punto 4 - Amazon Neptune (grafo de propiedades) con endpoint público + IAM.

Uso (desde la raíz del repositorio):
    uv run python punto4_neptune/neptune_grafo.py todo      # crear, cargar, consultar, costos
    uv run python punto4_neptune/neptune_grafo.py limpiar   # elimina todo y verifica

Pasos individuales: crear | estado | cargar | consultar | costos | limpiar

Acceso desde el computador local SIN instancia EC2:
- Neptune >= 1.4.6 permite endpoints públicos a nivel de instancia (PubliclyAccessible).
- Exige autenticación IAM: cada petición se firma con SigV4 (boto3 'neptunedata' lo hace
  automáticamente con las credenciales del perfil de AWS CLI). No hay contraseña de BD,
  por eso este punto no necesita un secreto en Secrets Manager.
- El grupo de seguridad solo abre el puerto 8182 a la IP pública actual (/32).
- La instancia queda en subredes públicas de la VPC por defecto (ruta 0.0.0.0/0 -> IGW).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from botocore.config import Config  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

from comun.precios import REFERENCIA, consultar_seguro  # noqa: E402
from comun.utilidades import (PREFIJO, REGION, Estado, Evidencia, cliente,  # noqa: E402
                              esperar, identidad, mi_ip_publica, sesion, vpc_por_defecto)

AQUI = pathlib.Path(__file__).resolve().parent
EV = Evidencia("punto4")
ESTADO = Estado("punto4")

CLUSTER = f"{PREFIJO}-neptune"
INSTANCIA = f"{PREFIJO}-neptune-1"
SUBNET_GROUP = f"{PREFIJO}-neptune-subnets"
SG_NOMBRE = f"{PREFIJO}-neptune-sg"
CLASES_PREFERIDAS = ["db.t4g.medium", "db.t3.medium"]  # las más baratas (y en capa gratuita)
VERSION_MINIMA = (1, 4, 6)


def _v(version: str) -> tuple:
    return tuple(int(x) for x in version.split(".")[:4] if x.isdigit())


# ----------------------------------------------------------------- creación
def crear() -> None:
    EV.titulo("Paso 1 - Red, seguridad y clúster Neptune con endpoint público")
    EV.paso("identidad_usada", identidad())
    nep, ec2 = cliente("neptune"), cliente("ec2")

    versiones = [v["EngineVersion"] for v in
                 nep.describe_db_engine_versions(Engine="neptune")["DBEngineVersions"]]
    validas = sorted([v for v in versiones if _v(v) >= VERSION_MINIMA], key=_v)
    if not validas:
        raise RuntimeError(f"No hay versión >= 1.4.6 en {REGION}: {versiones}")
    # La lista de clases ordenables viene paginada: se pregunta por cada clase directamente
    # y, si la versión más nueva no la ofrece, se prueba con versiones anteriores (>= 1.4.6).
    version = clase = None
    opciones = []
    for v in reversed(validas):
        for c in CLASES_PREFERIDAS:
            opciones = nep.describe_orderable_db_instance_options(
                Engine="neptune", EngineVersion=v, DBInstanceClass=c
            )["OrderableDBInstanceOptions"]
            if opciones:
                version, clase = v, c
                break
        if clase:
            break
    if clase is None:
        raise RuntimeError(f"Ninguna versión >= 1.4.6 ofrece {CLASES_PREFERIDAS} en {REGION}: "
                           f"{validas}")
    zonas = {z["Name"] for o in opciones for z in o.get("AvailabilityZones", [])}
    EV.nota(f"Versión del motor: {version} (públicos desde 1.4.6) | clase: {clase}")
    EV.paso("versiones_y_clases", {"versiones_disponibles": versiones, "elegida": version,
                                    "clase": clase, "zonas_clase": sorted(zonas)})

    vpc_id, subredes = vpc_por_defecto()
    subredes = [s for s in subredes if not zonas or s["AvailabilityZone"] in zonas]
    rutas = ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    EV.paso("vpc_rutas", {"vpc": vpc_id, "route_tables": rutas["RouteTables"],
                          "subredes": [{k: s[k] for k in ("SubnetId", "AvailabilityZone",
                                                          "CidrBlock", "MapPublicIpOnLaunch")}
                                       for s in subredes]})
    igw = [r.get("GatewayId") for t in rutas["RouteTables"] for r in t["Routes"]
           if r.get("DestinationCidrBlock") == "0.0.0.0/0"]
    EV.nota(f"VPC por defecto {vpc_id}: ruta 0.0.0.0/0 -> {igw} (subredes públicas)")

    try:
        nep.create_db_subnet_group(
            DBSubnetGroupName=SUBNET_GROUP,
            DBSubnetGroupDescription="Subredes publicas de la VPC por defecto (taller)",
            SubnetIds=[s["SubnetId"] for s in subredes])
    except ClientError as e:
        if "AlreadyExists" not in str(e):
            raise
    EV.paso("subnet_group", nep.describe_db_subnet_groups(DBSubnetGroupName=SUBNET_GROUP))

    ip = mi_ip_publica()
    try:
        sg = ec2.create_security_group(GroupName=SG_NOMBRE, VpcId=vpc_id,
                                       Description="Neptune 8182 solo desde la IP del estudiante")["GroupId"]
        ec2.authorize_security_group_ingress(GroupId=sg, IpPermissions=[{
            "IpProtocol": "tcp", "FromPort": 8182, "ToPort": 8182,
            "IpRanges": [{"CidrIp": f"{ip}/32", "Description": "IP publica del estudiante"}]}])
    except ClientError as e:
        if "Duplicate" not in str(e):
            raise
        sg = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [SG_NOMBRE]},
                                                   {"Name": "vpc-id", "Values": [vpc_id]}]
                                          )["SecurityGroups"][0]["GroupId"]
    ESTADO["sg"] = sg
    EV.paso("security_group", ec2.describe_security_groups(GroupIds=[sg]))
    EV.nota(f"Grupo de seguridad {sg}: TCP 8182 solo desde {ip}/32")

    try:
        nep.create_db_cluster(
            DBClusterIdentifier=CLUSTER, Engine="neptune", EngineVersion=version,
            DBSubnetGroupName=SUBNET_GROUP, VpcSecurityGroupIds=[sg],
            EnableIAMDatabaseAuthentication=True,   # obligatorio para endpoint público
            StorageEncrypted=True, BackupRetentionPeriod=1, DeletionProtection=False,
            Tags=[{"Key": "proyecto", "Value": PREFIJO}])
    except nep.exceptions.DBClusterAlreadyExistsFault:
        pass
    try:
        nep.create_db_instance(
            DBInstanceIdentifier=INSTANCIA, DBInstanceClass=clase, Engine="neptune",
            DBClusterIdentifier=CLUSTER, PubliclyAccessible=True,
            Tags=[{"Key": "proyecto", "Value": PREFIJO}])
    except nep.exceptions.DBInstanceAlreadyExistsFault:
        pass
    ESTADO["inicio"] = dt.datetime.now(dt.timezone.utc).isoformat()
    ESTADO["clase"] = clase

    def instancia_lista():
        i = nep.describe_db_instances(DBInstanceIdentifier=INSTANCIA)["DBInstances"][0]
        return i if i["DBInstanceStatus"] == "available" else None
    esperar(instancia_lista, "instancia Neptune disponible (10-15 min)", 30, 3600)
    cl = nep.describe_db_clusters(DBClusterIdentifier=CLUSTER)["DBClusters"][0]
    inst = nep.describe_db_instances(DBInstanceIdentifier=INSTANCIA)["DBInstances"][0]
    ESTADO["endpoint"] = cl["Endpoint"]
    EV.paso("cluster", cl)
    EV.paso("instancia", inst)
    EV.nota(f"Endpoint del clúster: {cl['Endpoint']}:{cl['Port']} | "
            f"IAM auth={cl.get('IAMDatabaseAuthenticationEnabled')} | "
            f"PubliclyAccessible={inst.get('PubliclyAccessible')}")
    estado()


# ------------------------------------------------------------- conexión
def datos_cli():
    if not ESTADO.get("endpoint"):
        cl = cliente("neptune").describe_db_clusters(DBClusterIdentifier=CLUSTER)["DBClusters"][0]
        ESTADO["endpoint"] = cl["Endpoint"]
    return sesion().client("neptunedata", endpoint_url=f"https://{ESTADO['endpoint']}:8182",
                           config=Config(retries={"max_attempts": 1}, read_timeout=120))


def estado() -> None:
    EV.titulo("Prueba de conexión desde el computador local (HTTPS + SigV4)")
    st = datos_cli().get_engine_status()
    EV.paso("engine_status", st)
    EV.nota(f"Estado: {st.get('status')} | versión {st.get('dbEngineVersion')} | "
            f"IAMAuthentication: {st.get('features', {}).get('IAMAuthentication')}")


def cypher(q: str, parametros: dict | None = None) -> list:
    kw = {"openCypherQuery": q}
    if parametros:
        kw["parameters"] = json.dumps(parametros, ensure_ascii=False)
    return datos_cli().execute_open_cypher_query(**kw).get("results", [])


def cargar() -> None:
    EV.titulo("Paso 2 - Carga del grafo (openCypher)")
    g = json.loads((AQUI / "grafo.json").read_text(encoding="utf-8"))
    cypher("MATCH (n) DETACH DELETE n")  # deja el grafo vacío (re-ejecutable)
    for etiqueta, vertices in g["vertices"].items():
        props = sorted({k for v in vertices for k in v})
        asignacion = ", ".join(f"{k}: v.{k}" for k in props)
        cypher(f"UNWIND $filas AS v CREATE (:{etiqueta} {{{asignacion}}})", {"filas": vertices})
        EV.nota(f"{len(vertices)} vértices :{etiqueta}")
    for tipo, aristas in g["aristas"].items():
        props = sorted({k for a in aristas for k in a} - {"de", "a"})
        asignacion = (" {" + ", ".join(f"{k}: r.{k}" for k in props) + "}") if props else ""
        cypher(f"UNWIND $filas AS r MATCH (x {{codigo: r.de}}), (y {{codigo: r.a}}) "
               f"CREATE (x)-[:{tipo}{asignacion}]->(y)", {"filas": aristas})
        EV.nota(f"{len(aristas)} aristas :{tipo}")
    v = cypher("MATCH (n) RETURN labels(n)[0] AS etiqueta, count(*) AS total ORDER BY etiqueta")
    e = cypher("MATCH ()-[r]->() RETURN type(r) AS tipo, count(*) AS total ORDER BY tipo")
    EV.tabla("conteo_vertices", ["etiqueta", "total"], [[x["etiqueta"], x["total"]] for x in v])
    EV.tabla("conteo_aristas", ["tipo", "total"], [[x["tipo"], x["total"]] for x in e])
    EV.nota(f"Total: {sum(x['total'] for x in v)} vértices y {sum(x['total'] for x in e)} relaciones")
    EV.texto("modelo_grafo.md", modelo_mermaid(g))


def modelo_mermaid(g: dict) -> str:
    nombres = {x["codigo"]: x["nombre"] for vs in g["vertices"].values() for x in vs}
    lineas = ["# Modelo del grafo", "", "## Esquema (tipos de vértice y relación)", "",
              "```mermaid", "graph LR",
              "  Estudiante -- CONOCE --> Estudiante",
              "  Estudiante -- \"INSCRITO_EN {nota}\" --> Curso",
              "  Profesor -- DICTA --> Curso",
              "  Curso -- REQUIERE --> Curso",
              "  Estudiante -- VIVE_EN --> Ciudad",
              "  Profesor -- VIVE_EN --> Ciudad", "```", "",
              "## Instancia (datos cargados)", "", "```mermaid", "graph LR"]
    for etq, vs in g["vertices"].items():
        for x in vs:
            lineas.append(f"  {x['codigo']}[\"{x['nombre']}<br/>:{etq}\"]")
    for tipo, aristas in g["aristas"].items():
        for a in aristas:
            lineas.append(f"  {a['de']} -- {tipo} --> {a['a']}")
    lineas += ["```", "", f"Vértices: {len(nombres)} | Aristas: "
               f"{sum(len(a) for a in g['aristas'].values())}"]
    return "\n".join(lineas) + "\n"


def leer_bloques(archivo: str) -> list[dict]:
    bloques, actual = [], None
    for ln in (AQUI / archivo).read_text(encoding="utf-8").splitlines():
        if ln.startswith("// name:"):
            actual = {"nombre": ln.split(":", 1)[1].strip(), "pregunta": "", "q": ""}
            bloques.append(actual)
        elif ln.startswith("// pregunta:") and actual:
            actual["pregunta"] = ln.split(":", 1)[1].strip()
        elif actual is not None and ln.strip():
            actual["q"] += ln + "\n"
    for b in bloques:
        b["q"] = b["q"].strip().rstrip(";")
    return bloques


def _formatear(v):
    if isinstance(v, list):
        return " -> ".join(_formatear(x) for x in v)
    if isinstance(v, dict) and "~properties" in v:
        return v["~properties"].get("nombre", v.get("~id"))
    return v


def consultar() -> None:
    EV.titulo("Paso 3 - Consultas que recorren relaciones (Python + openCypher y Gremlin)")
    for b in leer_bloques("consultas.cypher"):
        EV.nota(f"**{b['nombre']}** - {b['pregunta']}")
        try:
            t0 = time.time()
            res = cypher(b["q"])
            ms = (time.time() - t0) * 1000
            EV.paso(f"cypher_{b['nombre']}", {"consulta": b["q"], "resultado": res,
                                               "ms_ida_y_vuelta": ms}, mostrar=False)
            cols = list(res[0].keys()) if res else ["(sin resultados)"]
            EV.tabla(b["nombre"], cols, [[_formatear(r[c]) for c in cols] for r in res],
                     f"{b['pregunta']} ({ms:.0f} ms)")
        except ClientError as e:
            EV.nota(f"Error en {b['nombre']}: {e}")
    cli = datos_cli()
    for b in leer_bloques("consultas.gremlin"):
        try:
            r = cli.execute_gremlin_query(gremlinQuery=b["q"],
                                          serializer="application/vnd.gremlin-v1.0+json;types=false")
            datos = r.get("result", {}).get("data", r.get("result"))
            EV.paso(f"gremlin_{b['nombre']}", {"consulta": b["q"], "resultado": datos}, mostrar=False)
            EV.tabla(b["nombre"], ["resultado"], [[json.dumps(d, ensure_ascii=False)] for d in datos],
                     b["pregunta"])
        except ClientError as e:
            EV.nota(f"Error en {b['nombre']}: {e}")


def costos() -> None:
    EV.titulo("Paso 4 - Costos")
    clase = ESTADO.get("clase", "db.t4g.medium")
    precios = {"instancia": consultar_seguro("AmazonNeptune", [clase.split(".", 1)[1]]),
               "serverless": consultar_seguro("AmazonNeptune", ["serverless"]),
               "almacenamiento": consultar_seguro("AmazonNeptune", ["storage"])}
    EV.paso("precios_api", precios)
    precio_h = next((p["usd"] for p in precios["instancia"]
                     if p.get("usd") and "hour" in (p.get("unidad") or "").lower()), None)
    horas = 0.0
    if ESTADO.get("inicio"):
        horas = (dt.datetime.now(dt.timezone.utc) -
                 dt.datetime.fromisoformat(ESTADO["inicio"])).total_seconds() / 3600
    vol = None
    try:
        cw = cliente("cloudwatch").get_metric_statistics(
            Namespace="AWS/Neptune", MetricName="VolumeBytesUsed",
            Dimensions=[{"Name": "DBClusterIdentifier", "Value": CLUSTER}],
            StartTime=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3),
            EndTime=dt.datetime.now(dt.timezone.utc), Period=300, Statistics=["Maximum"])
        if cw["Datapoints"]:
            vol = max(d["Maximum"] for d in cw["Datapoints"])
    except ClientError:
        pass
    ph = precio_h or 0.098
    gb = (vol or 0) / 1024 ** 3
    filas = [
        [f"Instancia {clase} (aprovisionada)", f"{ph} USD/h" + ("" if precio_h else " (ref.)"),
         f"1 h: ${ph:.3f} | semana: ${ph * 168:.2f} | uso real ~{horas:.2f} h: ${ph * horas:.3f}"],
        ["Serverless mínimo 1 NCU (comparación)", f"{REFERENCIA['neptune_ncu_hora']} USD/NCU-h",
         f"1 h: ${REFERENCIA['neptune_ncu_hora']:.3f} | semana: ${REFERENCIA['neptune_ncu_hora'] * 168:.2f}"],
        ["Almacenamiento", f"{gb:.4f} GB usados (VolumeBytesUsed)",
         f"${gb * REFERENCIA['neptune_gb_mes']:.4f}/mes"],
        ["I/O", "pocas miles de peticiones", f"{REFERENCIA['neptune_millon_io']} USD/millón -> ~$0.00"],
        ["Endpoint público", "sin EC2 ni túnel", "$0.00 adicional (solo transferencia de datos)"],
        ["Capa gratuita (cuentas nuevas)", "750 h t3/t4g.medium por 30 días", "posible $0"],
    ]
    EV.tabla("estimacion_costos", ["componente", "uso", "costo_usd"], filas)


def limpiar() -> None:
    EV.titulo("Limpieza - eliminación y verificación")
    nep, ec2 = cliente("neptune"), cliente("ec2")
    try:
        nep.delete_db_instance(DBInstanceIdentifier=INSTANCIA)
        EV.nota("Solicitada eliminación de la instancia")

        def sin_instancia():
            try:
                nep.describe_db_instances(DBInstanceIdentifier=INSTANCIA)
                return False
            except nep.exceptions.DBInstanceNotFoundFault:
                return True
        esperar(sin_instancia, "instancia eliminada", 30, 3600)
    except nep.exceptions.DBInstanceNotFoundFault:
        EV.nota("La instancia no existía")
    try:
        nep.delete_db_cluster(DBClusterIdentifier=CLUSTER, SkipFinalSnapshot=True)
        EV.nota("Solicitada eliminación del clúster (sin snapshot final)")

        def sin_cluster():
            try:
                nep.describe_db_clusters(DBClusterIdentifier=CLUSTER)
                return False
            except nep.exceptions.DBClusterNotFoundFault:
                return True
        esperar(sin_cluster, "clúster eliminado", 30, 3600)
    except nep.exceptions.DBClusterNotFoundFault:
        EV.nota("El clúster no existía")
    try:
        nep.delete_db_subnet_group(DBSubnetGroupName=SUBNET_GROUP)
    except ClientError as e:
        EV.nota(f"Subnet group: {e.response['Error']['Code']}")
    sg = ESTADO.get("sg")
    if sg:
        for _ in range(10):  # las interfaces de red tardan en liberarse
            try:
                ec2.delete_security_group(GroupId=sg)
                break
            except ClientError as e:
                if "DependencyViolation" not in str(e):
                    EV.nota(f"SG: {e.response['Error']['Code']}")
                    break
                time.sleep(30)

    def existe(fn):
        try:
            fn()
            return "SIGUE EXISTIENDO"
        except ClientError as e:
            return f"no existe ({e.response['Error']['Code']})"

    try:
        snaps = nep.describe_db_cluster_snapshots(
            DBClusterIdentifier=CLUSTER).get("DBClusterSnapshots", [])
    except ClientError:
        snaps = []
    verif = [
        ["Instancia", existe(lambda: nep.describe_db_instances(DBInstanceIdentifier=INSTANCIA))],
        ["Clúster", existe(lambda: nep.describe_db_clusters(DBClusterIdentifier=CLUSTER))],
        ["Snapshots del clúster", ", ".join(s["DBClusterSnapshotIdentifier"] for s in snaps) or "ninguno"],
        ["DB subnet group", existe(lambda: nep.describe_db_subnet_groups(DBSubnetGroupName=SUBNET_GROUP))],
        ["Security group", existe(lambda: ec2.describe_security_groups(GroupIds=[sg])) if sg else "no creado"],
    ]
    EV.tabla("verificacion_eliminacion", ["recurso", "estado"], verif)
    ESTADO.borrar()


PASOS = {"crear": crear, "estado": estado, "cargar": cargar, "consultar": consultar,
         "costos": costos, "limpiar": limpiar}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("paso", choices=list(PASOS) + ["todo"])
    a = ap.parse_args()
    print(f"Región: {REGION} | prefijo: {PREFIJO}")
    if a.paso == "todo":
        for p in ("crear", "cargar", "consultar", "costos"):
            PASOS[p]()
        print("\nListo. Revise evidencias/punto4/. Luego: "
              "uv run python punto4_neptune/neptune_grafo.py limpiar")
    else:
        PASOS[a.paso]()
