"""Punto 3 - Amazon DocumentDB + EC2 bastión + túnel SSH + TLS + Secrets Manager.

Uso (desde la raíz del repositorio):
    uv run python punto3_documentdb/documentdb.py todo                 # serverless 0.5-1 DCU
    uv run python punto3_documentdb/documentdb.py todo --provisionado  # db.t3.medium
    uv run python punto3_documentdb/documentdb.py limpiar

Pasos: crear | probar | costos | limpiar

- DocumentDB vive en la VPC por defecto sin acceso público. El grupo de seguridad de
  DocumentDB solo acepta 27017 desde el grupo de seguridad del bastión.
- El bastión EC2 (t3.micro, IP pública) solo acepta SSH (22) desde la IP actual (/32).
- La contraseña del usuario maestro la genera y guarda DocumentDB en Secrets Manager
  (ManageMasterUserPassword=True). El programa la lee en tiempo de ejecución.
- TLS está activo (parámetro tls=enabled). Se usa el certificado global-bundle.pem de AWS.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import socket
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from botocore.exceptions import ClientError  # noqa: E402

from comun.precios import consultar_seguro  # noqa: E402
from comun.utilidades import (PREFIJO, REGION, Estado, Evidencia, cliente,  # noqa: E402
                              esperar, identidad, mi_ip_publica, vpc_por_defecto)

AQUI = pathlib.Path(__file__).resolve().parent
EV = Evidencia("punto3")
ESTADO = Estado("punto3")

CLUSTER = f"{PREFIJO}-docdb"
INSTANCIA = f"{PREFIJO}-docdb-1"
SUBNET_GROUP = f"{PREFIJO}-docdb-subnets"
SG_BASTION = f"{PREFIJO}-p3-bastion-sg"
SG_DOCDB = f"{PREFIJO}-p3-docdb-sg"
LLAVE = f"{PREFIJO}-p3-bastion"
ARCHIVO_LLAVE = AQUI / ".llaves" / f"{LLAVE}.pem"
CA = AQUI / "global-bundle.pem"
URL_CA = "https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem"
PARAM_AMI = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
PUERTO_LOCAL = int(os.getenv("DOCDB_PUERTO_LOCAL", "27018"))

PRODUCTOS = [
    {"sku": "TEC-001", "nombre": "Portátil 14", "categoria": "Tecnologia", "precio": 3499000,
     "stock": 12, "etiquetas": ["oficina", "portatil"], "proveedor": {"nombre": "Andina", "ciudad": "Medellín"}},
    {"sku": "TEC-002", "nombre": "Mouse inalámbrico", "categoria": "Tecnologia", "precio": 89000,
     "stock": 150, "etiquetas": ["accesorio"], "proveedor": {"nombre": "Andina", "ciudad": "Medellín"}},
    {"sku": "TEC-003", "nombre": "Monitor 27", "categoria": "Tecnologia", "precio": 1290000,
     "stock": 30, "etiquetas": ["oficina", "pantalla"], "proveedor": {"nombre": "Caribe", "ciudad": "Barranquilla"}},
    {"sku": "TEC-004", "nombre": "Audífonos", "categoria": "Tecnologia", "precio": 349000,
     "stock": 60, "etiquetas": ["audio", "accesorio"], "proveedor": {"nombre": "Pacífico", "ciudad": "Cali"}},
    {"sku": "TEC-005", "nombre": "Teclado mecánico", "categoria": "Tecnologia", "precio": 420000,
     "stock": 45, "etiquetas": ["accesorio", "gamer"], "proveedor": {"nombre": "Andina", "ciudad": "Medellín"}},
    {"sku": "MUE-001", "nombre": "Silla ergonómica", "categoria": "Muebles", "precio": 899000,
     "stock": 20, "etiquetas": ["oficina"], "proveedor": {"nombre": "Maderas", "ciudad": "Bogotá"}},
    {"sku": "MUE-002", "nombre": "Escritorio en L", "categoria": "Muebles", "precio": 1150000,
     "stock": 8, "etiquetas": ["oficina"], "proveedor": {"nombre": "Maderas", "ciudad": "Bogotá"}},
    {"sku": "MUE-003", "nombre": "Estantería", "categoria": "Muebles", "precio": 510000,
     "stock": 15, "etiquetas": ["hogar"], "proveedor": {"nombre": "Maderas", "ciudad": "Bogotá"}},
    {"sku": "HOG-001", "nombre": "Lámpara LED", "categoria": "Hogar", "precio": 129000,
     "stock": 80, "etiquetas": ["hogar", "iluminacion"], "proveedor": {"nombre": "Pacífico", "ciudad": "Cali"}},
    {"sku": "HOG-002", "nombre": "Cafetera", "categoria": "Hogar", "precio": 459000,
     "stock": 25, "etiquetas": ["hogar", "cocina"], "proveedor": {"nombre": "Caribe", "ciudad": "Barranquilla"}},
    {"sku": "HOG-003", "nombre": "Licuadora", "categoria": "Hogar", "precio": 289000,
     "stock": 0, "etiquetas": ["cocina"], "proveedor": {"nombre": "Caribe", "ciudad": "Barranquilla"}},
    {"sku": "PAP-001", "nombre": "Cuaderno", "categoria": "Papeleria", "precio": 12500,
     "stock": 500, "etiquetas": ["escolar"], "proveedor": {"nombre": "Andina", "ciudad": "Medellín"}},
]


# ------------------------------------------------------------------ creación
def crear(provisionado: bool) -> None:
    EV.titulo(f"Paso 1 - Red, bastión EC2 y DocumentDB "
              f"({'aprovisionado db.t3.medium' if provisionado else 'Serverless 0.5-1 DCU'})")
    EV.paso("identidad_usada", identidad())
    ec2, doc = cliente("ec2"), cliente("docdb")
    vpc, subredes = vpc_por_defecto()
    ip = mi_ip_publica()

    # --- grupos de seguridad
    def sg(nombre, desc):
        try:
            return ec2.create_security_group(GroupName=nombre, Description=desc, VpcId=vpc)["GroupId"]
        except ClientError as e:
            if "Duplicate" not in str(e):
                raise
            return ec2.describe_security_groups(Filters=[
                {"Name": "group-name", "Values": [nombre]},
                {"Name": "vpc-id", "Values": [vpc]}])["SecurityGroups"][0]["GroupId"]

    sg_b = sg(SG_BASTION, "Bastion SSH solo desde la IP del estudiante")
    sg_d = sg(SG_DOCDB, "DocumentDB 27017 solo desde el bastion")
    ESTADO["sg_bastion"], ESTADO["sg_docdb"] = sg_b, sg_d
    for gid, permiso in ((sg_b, {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                                 "IpRanges": [{"CidrIp": f"{ip}/32", "Description": "IP estudiante"}]}),
                         (sg_d, {"IpProtocol": "tcp", "FromPort": 27017, "ToPort": 27017,
                                 "UserIdGroupPairs": [{"GroupId": sg_b, "Description": "bastion"}]})):
        try:
            ec2.authorize_security_group_ingress(GroupId=gid, IpPermissions=[permiso])
        except ClientError as e:
            if "Duplicate" not in str(e):
                raise
    EV.paso("security_groups", ec2.describe_security_groups(GroupIds=[sg_b, sg_d]))
    EV.nota(f"SG bastión {sg_b}: 22/tcp desde {ip}/32 | SG DocumentDB {sg_d}: 27017/tcp desde {sg_b}")

    # --- llave SSH y bastión
    ARCHIVO_LLAVE.parent.mkdir(exist_ok=True)
    if not ARCHIVO_LLAVE.exists():
        try:
            k = ec2.create_key_pair(KeyName=LLAVE, KeyType="rsa", KeyFormat="pem")
            ARCHIVO_LLAVE.write_text(k["KeyMaterial"])
            os.chmod(ARCHIVO_LLAVE, 0o600)
        except ClientError as e:
            if "Duplicate" in str(e):
                raise SystemExit(f"El par de llaves {LLAVE} existe en AWS pero no en "
                                 f"{ARCHIVO_LLAVE}. Elimínelo con 'limpiar' y repita.")
            raise
    EV.nota(f"Llave privada guardada localmente en {ARCHIVO_LLAVE.relative_to(AQUI.parent)} "
            "(excluida del repositorio)")
    if not ESTADO.get("ec2"):
        ami = cliente("ssm").get_parameter(Name=PARAM_AMI)["Parameter"]["Value"]
        ESTADO["ec2"] = ec2.run_instances(
            ImageId=ami, InstanceType="t3.micro", MinCount=1, MaxCount=1, KeyName=LLAVE,
            NetworkInterfaces=[{"DeviceIndex": 0, "SubnetId": subredes[0]["SubnetId"],
                                "Groups": [sg_b], "AssociatePublicIpAddress": True}],
            MetadataOptions={"HttpTokens": "required"},
            TagSpecifications=[{"ResourceType": "instance", "Tags": [
                {"Key": "Name", "Value": f"{PREFIJO}-p3-bastion"},
                {"Key": "proyecto", "Value": PREFIJO}]}])["Instances"][0]["InstanceId"]

    # --- DocumentDB
    try:
        doc.create_db_subnet_group(DBSubnetGroupName=SUBNET_GROUP,
                                   DBSubnetGroupDescription="Subredes VPC por defecto",
                                   SubnetIds=[s["SubnetId"] for s in subredes])
    except ClientError as e:
        if "AlreadyExists" not in str(e):
            raise
    params = dict(DBClusterIdentifier=CLUSTER, Engine="docdb", EngineVersion="5.0.0",
                  MasterUsername="docdbadmin", ManageMasterUserPassword=True,
                  VpcSecurityGroupIds=[sg_d], DBSubnetGroupName=SUBNET_GROUP,
                  StorageEncrypted=True, DeletionProtection=False, BackupRetentionPeriod=1,
                  Tags=[{"Key": "proyecto", "Value": PREFIJO}])
    if not provisionado:
        params["ServerlessV2ScalingConfiguration"] = {"MinCapacity": 0.5, "MaxCapacity": 1.0}
    try:
        doc.create_db_cluster(**params)
    except doc.exceptions.DBClusterAlreadyExistsFault:
        pass
    clase = "db.t3.medium" if provisionado else "db.serverless"
    try:
        doc.create_db_instance(DBInstanceIdentifier=INSTANCIA, DBInstanceClass=clase,
                               Engine="docdb", DBClusterIdentifier=CLUSTER)
    except doc.exceptions.DBInstanceAlreadyExistsFault:
        pass
    ESTADO["clase"] = clase
    ESTADO["inicio"] = time.time()

    ec2.get_waiter("instance_status_ok").wait(InstanceIds=[ESTADO["ec2"]])
    inst = ec2.describe_instances(InstanceIds=[ESTADO["ec2"]])["Reservations"][0]["Instances"][0]
    ESTADO["ec2_dns"] = inst["PublicDnsName"] or inst["PublicIpAddress"]
    EV.paso("bastion_ec2", inst)
    EV.nota(f"Bastión {ESTADO['ec2']} listo: {ESTADO['ec2_dns']}")

    def lista():
        i = doc.describe_db_instances(DBInstanceIdentifier=INSTANCIA)["DBInstances"][0]
        return i["DBInstanceStatus"] == "available"
    esperar(lista, "instancia DocumentDB disponible (10-15 min)", 30, 3600)
    cl = doc.describe_db_clusters(DBClusterIdentifier=CLUSTER)["DBClusters"][0]
    ESTADO["endpoint"] = cl["Endpoint"]
    ESTADO["secreto_arn"] = cl["MasterUserSecret"]["SecretArn"]
    EV.paso("docdb_cluster", cl)
    EV.paso("docdb_instancia", doc.describe_db_instances(DBInstanceIdentifier=INSTANCIA))
    grupo = cl["DBClusterParameterGroup"]
    tls = [p for p in doc.describe_db_cluster_parameters(DBClusterParameterGroupName=grupo)["Parameters"]
           if p["ParameterName"] == "tls"]
    EV.paso("parametro_tls", tls)
    EV.nota(f"Endpoint {cl['Endpoint']}:{cl['Port']} | TLS={tls[0]['ParameterValue'] if tls else '?'} | "
            f"secreto administrado {cl['MasterUserSecret']['SecretArn']}")
    if not CA.exists():
        urllib.request.urlretrieve(URL_CA, CA)
    EV.nota(f"Certificado de AWS descargado: {CA.name}")
    escribir_guia_compass()


def escribir_guia_compass() -> None:
    texto = f"""# Conexión desde MongoDB Compass (vía túnel SSH)

En Compass -> New connection -> Advanced Connection Options:

**General**
- Host: `{ESTADO.get('endpoint')}:27017`
- Direct connection: activado

**Authentication**: Username/Password
- Username: `docdbadmin`
- Password: valor de `password` del secreto `{ESTADO.get('secreto_arn')}`
  (consúltelo en la consola de Secrets Manager -> Retrieve secret value; NO lo guarde en el repositorio)
- Authentication Mechanism: SCRAM-SHA-1, Authentication Database: admin

**TLS/SSL**
- SSL/TLS Connection: On
- Certificate Authority (.pem): `punto3_documentdb/global-bundle.pem`
- (Compass resuelve el host a través del túnel, así que el nombre del certificado coincide)

**Proxy/SSH**: SSH with Identity File
- SSH Hostname: `{ESTADO.get('ec2_dns')}`  SSH Port: 22
- SSH Username: `ec2-user`
- SSH Identity File: `punto3_documentdb/.llaves/{LLAVE}.pem`

**Advanced**: Retry Writes = off (DocumentDB no soporta retryable writes)

Cadena equivalente (sin contraseña):
`mongodb://docdbadmin:<password>@{ESTADO.get('endpoint')}:27017/?tls=true&tlsCAFile=global-bundle.pem&directConnection=true&retryWrites=false&authMechanism=SCRAM-SHA-1`

Túnel manual alternativo (OpenSSH en WSL; copie antes la llave a ~/.ssh y aplique chmod 600):
```
ssh -i punto3_documentdb/.llaves/{LLAVE}.pem -N -L {PUERTO_LOCAL}:{ESTADO.get('endpoint')}:27017 ec2-user@{ESTADO.get('ec2_dns')}
```
y en Compass host `localhost:{PUERTO_LOCAL}` + TLS + `tlsAllowInvalidHostnames=true` (el certificado es del endpoint, no de localhost).
"""
    EV.texto("guia_compass.md", texto)


# ------------------------------------------------------------- conexión y CRUD
def credenciales() -> dict:
    """Lee usuario y contraseña de Secrets Manager en tiempo de ejecución."""
    r = cliente("secretsmanager").get_secret_value(SecretId=ESTADO["secreto_arn"])
    return json.loads(r["SecretString"])


def _puerto_libre(puerto: int) -> int:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", puerto))
            return puerto
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def probar() -> None:
    EV.titulo("Paso 2 - Conexión desde Python por túnel SSH + TLS y operaciones")
    from pymongo import ASCENDING, DESCENDING, MongoClient
    from sshtunnel import SSHTunnelForwarder

    cred = credenciales()
    EV.nota(f"Credenciales obtenidas de Secrets Manager para el usuario '{cred['username']}' "
            "(la contraseña no se muestra)")
    puerto = _puerto_libre(PUERTO_LOCAL)
    with SSHTunnelForwarder((ESTADO["ec2_dns"], 22), ssh_username="ec2-user",
                            ssh_pkey=str(ARCHIVO_LLAVE),
                            remote_bind_address=(ESTADO["endpoint"], 27017),
                            local_bind_address=("127.0.0.1", puerto)) as tunel:
        EV.nota(f"Túnel SSH activo: 127.0.0.1:{tunel.local_bind_port} -> {ESTADO['ec2_dns']}:22 "
                f"-> {ESTADO['endpoint']}:27017")
        cli = MongoClient(host="127.0.0.1", port=tunel.local_bind_port,
                          username=cred["username"], password=cred["password"],
                          authSource="admin", authMechanism="SCRAM-SHA-1",
                          tls=True, tlsCAFile=str(CA),
                          tlsAllowInvalidHostnames=True,  # el certificado es del endpoint, no de 127.0.0.1
                          directConnection=True, retryWrites=False,
                          serverSelectionTimeoutMS=20000)
        info = cli.server_info()
        EV.paso("server_info", {k: info.get(k) for k in ("version", "ok")})
        EV.nota(f"Conectado. Versión compatible MongoDB {info.get('version')}")

        bd = cli["taller"]
        col = bd["productos"]
        col.drop()
        r = col.insert_many(PRODUCTOS)
        col.create_index([("categoria", ASCENDING), ("precio", DESCENDING)])
        EV.nota(f"Base 'taller', colección 'productos': {len(r.inserted_ids)} documentos insertados")
        EV.paso("documentos_insertados", list(col.find({}, {"_id": 0})))

        filtro = {"categoria": "Tecnologia", "precio": {"$gte": 300000}, "stock": {"$gt": 0}}
        res = list(col.find(filtro, {"_id": 0, "sku": 1, "nombre": 1, "precio": 1, "stock": 1}))
        EV.texto("consulta_filtro.json", json.dumps(filtro, indent=2))
        EV.tabla("q1_filtro", ["sku", "nombre", "precio", "stock"],
                 [[d["sku"], d["nombre"], d["precio"], d["stock"]] for d in res],
                 "Tecnología con precio >= 300.000 y con stock")

        res = list(col.find({}, {"_id": 0, "nombre": 1, "categoria": 1, "precio": 1})
                   .sort([("precio", DESCENDING), ("nombre", ASCENDING)]).limit(5))
        EV.tabla("q2_ordenacion", ["nombre", "categoria", "precio"],
                 [[d["nombre"], d["categoria"], d["precio"]] for d in res],
                 "Los 5 productos más caros (sort precio desc)")

        pipeline = [
            {"$match": {"stock": {"$gt": 0}}},
            {"$group": {"_id": "$categoria", "productos": {"$sum": 1},
                        "precio_promedio": {"$avg": "$precio"},
                        "unidades": {"$sum": "$stock"},
                        "valor_inventario": {"$sum": {"$multiply": ["$precio", "$stock"]}}}},
            {"$sort": {"valor_inventario": -1}},
        ]
        EV.texto("consulta_agregacion.json", json.dumps(pipeline, indent=2))
        res = list(col.aggregate(pipeline))
        EV.tabla("q3_agregacion", ["categoria", "productos", "precio_promedio", "unidades",
                                   "valor_inventario"],
                 [[d["_id"], d["productos"], round(d["precio_promedio"]), d["unidades"],
                   d["valor_inventario"]] for d in res],
                 "Inventario por categoría (solo productos con stock)")

        pipeline2 = [{"$unwind": "$etiquetas"},
                     {"$group": {"_id": "$etiquetas", "n": {"$sum": 1}}},
                     {"$sort": {"n": -1, "_id": 1}}]
        res = list(col.aggregate(pipeline2))
        EV.tabla("q4_agregacion_etiquetas", ["etiqueta", "productos"],
                 [[d["_id"], d["n"]] for d in res], "Productos por etiqueta ($unwind + $group)")
        cli.close()


def costos() -> None:
    EV.titulo("Paso 3 - Costos")
    precios = {"docdb_serverless": consultar_seguro("AmazonDocDB", ["serverless"]),
               "docdb_t3_medium": consultar_seguro("AmazonDocDB", ["t3.medium"]),
               "ec2_t3_micro": consultar_seguro("AmazonEC2", ["t3.micro"], {
                   "instanceType": "t3.micro", "operatingSystem": "Linux", "tenancy": "Shared",
                   "preInstalledSw": "NA", "capacitystatus": "Used"})}
    EV.paso("precios_api", precios)
    dcu, t3m, ec2h, ipv4 = 0.0822, 0.078, 0.0104, 0.005
    horas = (time.time() - ESTADO.get("inicio", time.time())) / 3600
    filas = [
        ["DocumentDB Serverless (mín. 0.5 DCU)", f"0.5 x {dcu} USD/DCU-h", f"{0.5 * dcu:.4f}",
         f"{0.5 * dcu * 168:.2f}"],
        ["DocumentDB db.t3.medium aprovisionado", f"{t3m} USD/h (ref.)", f"{t3m:.4f}", f"{t3m * 168:.2f}"],
        ["Almacenamiento DocumentDB (<1 GB)", "0.10 USD/GB-mes", "~0.0001", "~0.02"],
        ["I/O DocumentDB Standard", "0.20 USD/millón", "~0", "~0"],
        ["Secreto administrado", "0.40 USD/mes", f"{0.4 / 730:.5f}", f"{0.4 / 730 * 168:.3f}"],
        ["EC2 bastión t3.micro", f"{ec2h} USD/h", f"{ec2h:.4f}", f"{ec2h * 168:.2f}"],
        ["IPv4 pública del bastión", f"{ipv4} USD/h", f"{ipv4:.4f}", f"{ipv4 * 168:.2f}"],
        ["EBS 8 GB del bastión", "0.08 USD/GB-mes", f"{8 * 0.08 / 730:.4f}", f"{8 * 0.08 / 730 * 168:.2f}"],
    ]
    EV.tabla("estimacion_costos", ["componente", "precio", "1_hora_USD", "1_semana_USD"], filas,
             f"us-east-1. Clase usada: {ESTADO.get('clase')}; tiempo activo ~{horas:.2f} h. "
             "Capa gratuita DocumentDB (1 mes): 750 h de db.t3.medium.")


def limpiar() -> None:
    EV.titulo("Limpieza - eliminación y verificación")
    ec2, doc = cliente("ec2"), cliente("docdb")
    try:
        doc.delete_db_instance(DBInstanceIdentifier=INSTANCIA)

        def sin_inst():
            try:
                doc.describe_db_instances(DBInstanceIdentifier=INSTANCIA)
                return False
            except doc.exceptions.DBInstanceNotFoundFault:
                return True
        esperar(sin_inst, "instancia DocumentDB eliminada", 30, 3600)
    except doc.exceptions.DBInstanceNotFoundFault:
        pass
    try:
        doc.delete_db_cluster(DBClusterIdentifier=CLUSTER, SkipFinalSnapshot=True)

        def sin_cl():
            try:
                doc.describe_db_clusters(DBClusterIdentifier=CLUSTER)
                return False
            except doc.exceptions.DBClusterNotFoundFault:
                return True
        esperar(sin_cl, "clúster DocumentDB eliminado", 30, 3600)
    except doc.exceptions.DBClusterNotFoundFault:
        pass
    try:
        doc.delete_db_subnet_group(DBSubnetGroupName=SUBNET_GROUP)
    except ClientError:
        pass
    if ESTADO.get("ec2"):
        ec2.terminate_instances(InstanceIds=[ESTADO["ec2"]])
        ec2.get_waiter("instance_terminated").wait(InstanceIds=[ESTADO["ec2"]])
    try:
        ec2.delete_key_pair(KeyName=LLAVE)
    except ClientError:
        pass
    for clave in ("sg_docdb", "sg_bastion"):
        if ESTADO.get(clave):
            for _ in range(10):
                try:
                    ec2.delete_security_group(GroupId=ESTADO[clave])
                    break
                except ClientError as e:
                    if "DependencyViolation" not in str(e):
                        break
                    time.sleep(30)

    def existe(fn):
        try:
            fn()
            return "SIGUE EXISTIENDO"
        except ClientError as e:
            return f"no existe ({e.response['Error']['Code']})"

    estado_ec2 = "no creada"
    if ESTADO.get("ec2"):
        estado_ec2 = ec2.describe_instances(InstanceIds=[ESTADO["ec2"]])["Reservations"][0][
            "Instances"][0]["State"]["Name"]
    secreto = "no aplica"
    if ESTADO.get("secreto_arn"):
        try:
            d = cliente("secretsmanager").describe_secret(SecretId=ESTADO["secreto_arn"])
            secreto = f"programado para borrar {d['DeletedDate']}" if d.get("DeletedDate") \
                else "SIGUE EXISTIENDO"
        except ClientError as e:
            secreto = f"no existe ({e.response['Error']['Code']})"
    verif = [
        ["Instancia DocumentDB", existe(lambda: doc.describe_db_instances(DBInstanceIdentifier=INSTANCIA))],
        ["Clúster DocumentDB", existe(lambda: doc.describe_db_clusters(DBClusterIdentifier=CLUSTER))],
        ["Subnet group", existe(lambda: doc.describe_db_subnet_groups(DBSubnetGroupName=SUBNET_GROUP))],
        ["Secreto administrado", secreto],
        ["EC2 bastión", estado_ec2],
        ["Par de llaves", existe(lambda: ec2.describe_key_pairs(KeyNames=[LLAVE]))],
        ["SG DocumentDB", existe(lambda: ec2.describe_security_groups(GroupIds=[ESTADO["sg_docdb"]]))
         if ESTADO.get("sg_docdb") else "no creado"],
        ["SG bastión", existe(lambda: ec2.describe_security_groups(GroupIds=[ESTADO["sg_bastion"]]))
         if ESTADO.get("sg_bastion") else "no creado"],
    ]
    EV.tabla("verificacion_eliminacion", ["recurso", "estado"], verif)
    if ARCHIVO_LLAVE.exists():
        ARCHIVO_LLAVE.unlink()
    ESTADO.borrar()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("paso", choices=["crear", "probar", "costos", "limpiar", "todo"])
    ap.add_argument("--provisionado", action="store_true",
                    help="usar db.t3.medium en vez de Serverless (útil con la prueba gratuita)")
    a = ap.parse_args()
    print(f"Región: {REGION}")
    if a.paso in ("crear", "todo"):
        crear(a.provisionado)
    if a.paso in ("probar", "todo"):
        probar()
    if a.paso in ("costos", "todo"):
        costos()
    if a.paso == "limpiar":
        limpiar()
    if a.paso == "todo":
        print("\nListo. Pruebe Compass con evidencias/punto3/guia_compass.md y luego: "
              "uv run python punto3_documentdb/documentdb.py limpiar")
