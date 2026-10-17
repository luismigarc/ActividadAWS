"""Punto 2 - Versión Boto3: S3 + EC2 + RDS (y su red) con el usuario user_cli.

    export AWS_PROFILE=user_cli
    uv run python punto2_terraform_sdk_cli/boto3/desplegar.py crear
    uv run python punto2_terraform_sdk_cli/boto3/desplegar.py eliminar

Mismos recursos que la versión Terraform:
  - Bucket S3 privado
  - SG de la EC2 (solo salida) y SG de RDS (5432 solo desde el SG de la EC2)
  - EC2 t3.micro con Amazon Linux 2023 (IMDSv2)
  - DB subnet group + RDS PostgreSQL db.t4g.micro con ManageMasterUserPassword=True
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from botocore.exceptions import ClientError  # noqa: E402

from comun.utilidades import (REGION, Estado, Evidencia, cliente, crear_bucket,  # noqa: E402
                              identidad, vaciar_y_borrar_bucket, vpc_por_defecto)
from comun_p2 import (ALMACENAMIENTO_GB, CLASE_RDS, MOTOR, PARAM_AMI, TIPO_EC2,  # noqa: E402
                      registrar_tiempo, verificar_recursos)

PREFIJO = "taller-ingdata-p2-sdk"
EV = Evidencia("punto2")
ESTADO = Estado("punto2_sdk")
TAGS = [{"Key": "proyecto", "Value": "taller-ingdata"}, {"Key": "metodo", "Value": "boto3"}]


def crear() -> None:
    EV.titulo("Versión Boto3 - creación")
    t0 = time.time()
    ident = identidad()
    EV.paso("sdk_identidad", ident)
    EV.nota(f"Identidad usada: {ident['Arn']} (perfil de AWS CLI, no la cuenta raíz)")
    ec2, rds = cliente("ec2"), cliente("rds")

    bucket = f"{PREFIJO}-{ident['Account']}"
    crear_bucket(bucket)
    ESTADO["bucket"] = bucket
    EV.nota(f"Bucket: {bucket}")

    vpc, subredes = vpc_por_defecto()
    sg_ec2 = ec2.create_security_group(
        GroupName=f"{PREFIJO}-ec2-sg", Description="EC2 del taller: sin entradas", VpcId=vpc,
        TagSpecifications=[{"ResourceType": "security-group", "Tags": TAGS}])["GroupId"]
    ESTADO["sg_ec2"] = sg_ec2
    sg_rds = ec2.create_security_group(
        GroupName=f"{PREFIJO}-rds-sg", Description="RDS: 5432 solo desde la EC2", VpcId=vpc,
        TagSpecifications=[{"ResourceType": "security-group", "Tags": TAGS}])["GroupId"]
    ESTADO["sg_rds"] = sg_rds
    ec2.authorize_security_group_ingress(GroupId=sg_rds, IpPermissions=[{
        "IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
        "UserIdGroupPairs": [{"GroupId": sg_ec2, "Description": "PostgreSQL desde la EC2"}]}])
    EV.nota(f"Security groups: {sg_ec2} (EC2), {sg_rds} (RDS)")

    ami = cliente("ssm").get_parameter(Name=PARAM_AMI)["Parameter"]["Value"]
    inst = ec2.run_instances(
        ImageId=ami, InstanceType=TIPO_EC2, MinCount=1, MaxCount=1,
        # Sin IPv4 pública (se cobra 0,005 USD/h); la EC2 no necesita entradas.
        NetworkInterfaces=[{"DeviceIndex": 0, "SubnetId": subredes[0]["SubnetId"],
                            "Groups": [sg_ec2], "AssociatePublicIpAddress": False}],
        MetadataOptions={"HttpTokens": "required"},
        BlockDeviceMappings=[{"DeviceName": "/dev/xvda",
                              "Ebs": {"VolumeSize": 8, "VolumeType": "gp3",
                                      "DeleteOnTermination": True}}],
        TagSpecifications=[{"ResourceType": "instance",
                            "Tags": TAGS + [{"Key": "Name", "Value": f"{PREFIJO}-ec2"}]}]
    )["Instances"][0]["InstanceId"]
    ESTADO["ec2"] = inst
    EV.nota(f"EC2 {inst} ({TIPO_EC2}, {ami})")

    rds.create_db_subnet_group(DBSubnetGroupName=f"{PREFIJO}-subnets",
                               DBSubnetGroupDescription="Subredes VPC por defecto",
                               SubnetIds=[s["SubnetId"] for s in subredes], Tags=TAGS)
    rds.create_db_instance(
        DBInstanceIdentifier=f"{PREFIJO}-rds", Engine=MOTOR, DBInstanceClass=CLASE_RDS,
        AllocatedStorage=ALMACENAMIENTO_GB, StorageType="gp3", StorageEncrypted=True,
        MasterUsername="dbadmin", ManageMasterUserPassword=True,   # contraseña en Secrets Manager
        DBSubnetGroupName=f"{PREFIJO}-subnets", VpcSecurityGroupIds=[sg_rds],
        PubliclyAccessible=False, MultiAZ=False, BackupRetentionPeriod=0,
        DeletionProtection=False, Tags=TAGS)
    EV.nota("RDS solicitado; esperando a que la EC2 y la base de datos estén disponibles…")
    ec2.get_waiter("instance_running").wait(InstanceIds=[inst])
    rds.get_waiter("db_instance_available").wait(
        DBInstanceIdentifier=f"{PREFIJO}-rds", WaiterConfig={"Delay": 30, "MaxAttempts": 80})
    db = rds.describe_db_instances(DBInstanceIdentifier=f"{PREFIJO}-rds")["DBInstances"][0]
    ESTADO["secreto_rds"] = db["MasterUserSecret"]["SecretArn"]
    EV.paso("sdk_rds", db)
    EV.paso("sdk_ec2", ec2.describe_instances(InstanceIds=[inst]))
    EV.nota(f"RDS {db['Endpoint']['Address']} | secreto administrado: "
            f"{db['MasterUserSecret']['SecretArn']} ({db['MasterUserSecret']['SecretStatus']})")
    seg = time.time() - t0
    registrar_tiempo("boto3", "crear", seg)
    EV.nota(f"Tiempo total de creación: {seg:.0f} s")


def eliminar() -> None:
    EV.titulo("Versión Boto3 - eliminación")
    t0 = time.time()
    ec2, rds = cliente("ec2"), cliente("rds")
    try:
        rds.delete_db_instance(DBInstanceIdentifier=f"{PREFIJO}-rds", SkipFinalSnapshot=True,
                               DeleteAutomatedBackups=True)
    except ClientError as e:
        EV.nota(f"RDS: {e.response['Error']['Code']}")
    if ESTADO.get("ec2"):
        ec2.terminate_instances(InstanceIds=[ESTADO["ec2"]])
        ec2.get_waiter("instance_terminated").wait(InstanceIds=[ESTADO["ec2"]])
        EV.nota(f"EC2 {ESTADO['ec2']} terminada")
    rds.get_waiter("db_instance_deleted").wait(
        DBInstanceIdentifier=f"{PREFIJO}-rds", WaiterConfig={"Delay": 30, "MaxAttempts": 80})
    EV.nota("RDS eliminado")
    for fn, desc in ((lambda: rds.delete_db_subnet_group(DBSubnetGroupName=f"{PREFIJO}-subnets"),
                      "DB subnet group"),
                     (lambda: ec2.delete_security_group(GroupId=ESTADO["sg_rds"]), "SG RDS"),
                     (lambda: ec2.delete_security_group(GroupId=ESTADO["sg_ec2"]), "SG EC2")):
        for _ in range(10):
            try:
                fn()
                EV.nota(f"{desc} eliminado")
                break
            except ClientError as e:
                if e.response["Error"]["Code"] != "DependencyViolation":
                    EV.nota(f"{desc}: {e.response['Error']['Code']}")
                    break
                time.sleep(20)
    vaciar_y_borrar_bucket(ESTADO["bucket"])
    EV.nota(f"Bucket {ESTADO['bucket']} eliminado")
    seg = time.time() - t0
    registrar_tiempo("boto3", "eliminar", seg)
    EV.tabla("sdk_verificacion_eliminacion", ["recurso", "estado"],
             verificar_recursos(PREFIJO, ESTADO.get("secreto_rds")))
    ESTADO.borrar()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["crear", "eliminar"])
    print(f"Región: {REGION}")
    {"crear": crear, "eliminar": eliminar}[ap.parse_args().accion]()
