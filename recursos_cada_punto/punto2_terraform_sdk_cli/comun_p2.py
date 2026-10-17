"""Configuración y utilidades compartidas por las tres versiones del punto 2."""
from __future__ import annotations

import csv
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from botocore.exceptions import ClientError  # noqa: E402

from comun.utilidades import RAIZ, cliente  # noqa: E402

TIPO_EC2 = "t3.micro"
CLASE_RDS = "db.t4g.micro"
MOTOR = "postgres"
ALMACENAMIENTO_GB = 20
PARAM_AMI = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
TIEMPOS = RAIZ / "evidencias" / "punto2" / "tiempos.csv"


def registrar_tiempo(metodo: str, accion: str, segundos: float) -> None:
    nuevo = not TIEMPOS.exists()
    TIEMPOS.parent.mkdir(parents=True, exist_ok=True)
    with TIEMPOS.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["fecha", "metodo", "accion", "segundos"])
        w.writerow([dt.datetime.now().isoformat(timespec="seconds"), metodo, accion,
                    round(segundos)])


def verificar_recursos(prefijo: str, secreto_arn: str | None = None) -> list[list[str]]:
    """Comprueba si quedan recursos con el prefijo dado (bucket, EC2, RDS, SG, subnet group)."""
    s3, ec2, rds = cliente("s3"), cliente("ec2"), cliente("rds")
    filas = []
    buckets = [b["Name"] for b in s3.list_buckets()["Buckets"] if b["Name"].startswith(prefijo)]
    filas.append(["Bucket S3", ", ".join(buckets) or "ninguno"])
    inst = ec2.describe_instances(Filters=[
        {"Name": "tag:Name", "Values": [f"{prefijo}*"]},
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped",
                                                   "shutting-down"]}])
    ids = [i["InstanceId"] for r in inst["Reservations"] for i in r["Instances"]]
    filas.append(["Instancias EC2 activas", ", ".join(ids) or "ninguna (o terminated)"])
    dbs = [d["DBInstanceIdentifier"] for d in rds.describe_db_instances()["DBInstances"]
           if d["DBInstanceIdentifier"].startswith(prefijo)]
    filas.append(["Instancias RDS", ", ".join(dbs) or "ninguna"])
    sgs = [g["GroupName"] for g in ec2.describe_security_groups(Filters=[
        {"Name": "group-name", "Values": [f"{prefijo}*"]}])["SecurityGroups"]]
    filas.append(["Security groups", ", ".join(sgs) or "ninguno"])
    try:
        rds.describe_db_subnet_groups(DBSubnetGroupName=f"{prefijo}-subnets")
        filas.append(["DB subnet group", "SIGUE EXISTIENDO"])
    except ClientError:
        filas.append(["DB subnet group", "no existe"])
    snaps = [s["DBSnapshotIdentifier"] for s in rds.describe_db_snapshots()["DBSnapshots"]
             if s["DBSnapshotIdentifier"].startswith(prefijo)]
    filas.append(["Snapshots RDS", ", ".join(snaps) or "ninguno"])
    if secreto_arn:
        try:
            d = cliente("secretsmanager").describe_secret(SecretId=secreto_arn)
            filas.append(["Secreto RDS", f"programado para borrar {d.get('DeletedDate')}"
                          if d.get("DeletedDate") else "SIGUE EXISTIENDO"])
        except ClientError as e:
            filas.append(["Secreto RDS", f"no existe ({e.response['Error']['Code']})"])
    return filas
