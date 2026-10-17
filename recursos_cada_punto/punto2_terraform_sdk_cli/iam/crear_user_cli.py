"""Crea el usuario IAM `user_cli` con la política mínima del punto 2 y configura su perfil.

Se ejecuta UNA vez con un usuario administrador (no la cuenta raíz):
    AWS_PROFILE=admin uv run python punto2_terraform_sdk_cli/iam/crear_user_cli.py crear
Al terminar el taller:
    AWS_PROFILE=admin uv run python punto2_terraform_sdk_cli/iam/crear_user_cli.py eliminar

La clave de acceso se escribe DIRECTAMENTE en el perfil `user_cli` de AWS CLI
(~/.aws/credentials de WSL) con `aws configure set`; nunca se imprime ni se guarda
en el repositorio ni en Secrets Manager (las herramientas necesitan autenticarse en AWS
antes de poder leer cualquier secreto).
"""
import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from comun.utilidades import REGION, Evidencia, cliente, identidad  # noqa: E402

USUARIO = "user_cli"
POLITICA = "taller-ingdata-user-cli-policy"
AQUI = pathlib.Path(__file__).parent
EV = Evidencia("punto2")


def crear():
    EV.titulo("IAM - creación de user_cli (ejecutado con un administrador)")
    EV.paso("identidad_administrador", identidad())
    iam = cliente("iam")
    doc = (AQUI / "politica_user_cli.json").read_text(encoding="utf-8").replace("us-east-1", REGION)
    cuenta = identidad()["Account"]
    try:
        iam.create_user(UserName=USUARIO, Tags=[{"Key": "proyecto", "Value": "taller-ingdata"}])
    except iam.exceptions.EntityAlreadyExistsException:
        pass
    arn_pol = f"arn:aws:iam::{cuenta}:policy/{POLITICA}"
    try:
        iam.create_policy(PolicyName=POLITICA, PolicyDocument=doc,
                          Description="Permisos mínimos del punto 2 (S3, EC2, RDS y red)")
    except iam.exceptions.EntityAlreadyExistsException:
        # nueva versión de la política (máximo 5 versiones)
        vers = iam.list_policy_versions(PolicyArn=arn_pol)["Versions"]
        for v in vers:
            if not v["IsDefaultVersion"] and len(vers) >= 5:
                iam.delete_policy_version(PolicyArn=arn_pol, VersionId=v["VersionId"])
                break
        iam.create_policy_version(PolicyArn=arn_pol, PolicyDocument=doc, SetAsDefault=True)
    iam.attach_user_policy(UserName=USUARIO, PolicyArn=arn_pol)
    EV.paso("user_cli", iam.get_user(UserName=USUARIO)["User"])
    EV.paso("user_cli_politicas", iam.list_attached_user_policies(UserName=USUARIO))
    EV.texto("politica_user_cli.json", doc)

    if iam.list_access_keys(UserName=USUARIO)["AccessKeyMetadata"]:
        print("user_cli ya tiene una clave de acceso; no se crea otra.")
        return
    clave = iam.create_access_key(UserName=USUARIO)["AccessKey"]
    for k, v in (("aws_access_key_id", clave["AccessKeyId"]),
                 ("aws_secret_access_key", clave["SecretAccessKey"]),
                 ("region", REGION), ("output", "json")):
        subprocess.run(["aws", "configure", "set", k, v, "--profile", USUARIO], check=True)
    EV.nota(f"Clave {clave['AccessKeyId'][:4]}…{clave['AccessKeyId'][-4:]} guardada en el perfil "
            f"'{USUARIO}' de AWS CLI (archivo ~/.aws/credentials, fuera del repositorio)")
    print("\nAhora use:  export AWS_PROFILE=user_cli  y verifique con  aws sts get-caller-identity")


def eliminar():
    EV.titulo("IAM - eliminación de user_cli")
    iam = cliente("iam")
    cuenta = identidad()["Account"]
    arn_pol = f"arn:aws:iam::{cuenta}:policy/{POLITICA}"
    try:
        for k in iam.list_access_keys(UserName=USUARIO)["AccessKeyMetadata"]:
            iam.delete_access_key(UserName=USUARIO, AccessKeyId=k["AccessKeyId"])
        iam.detach_user_policy(UserName=USUARIO, PolicyArn=arn_pol)
        iam.delete_user(UserName=USUARIO)
    except iam.exceptions.NoSuchEntityException:
        pass
    try:
        for v in iam.list_policy_versions(PolicyArn=arn_pol)["Versions"]:
            if not v["IsDefaultVersion"]:
                iam.delete_policy_version(PolicyArn=arn_pol, VersionId=v["VersionId"])
        iam.delete_policy(PolicyArn=arn_pol)
    except iam.exceptions.NoSuchEntityException:
        pass
    EV.nota("user_cli, sus claves y su política eliminados")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["crear", "eliminar"])
    {"crear": crear, "eliminar": eliminar}[ap.parse_args().accion]()
