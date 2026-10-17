"""Programa lector: obtiene un secreto de Secrets Manager en tiempo de ejecución.

No contiene contraseñas: solo el NOMBRE del secreto. Cada lectura pide la versión
AWSCURRENT, así que si el valor cambia (put_secret_value o rotación) el programa recibe
el valor nuevo sin tocar el código. Incluye una caché opcional en memoria con TTL.

Uso directo (con el rol de mínimo privilegio del punto 1):
    uv run python punto1_secrets_manager/lector_secreto.py taller/punto1/db-ficticia --rol <ARN>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

import boto3


def huella(texto: str) -> str:
    """Huella corta para comprobar cambios sin revelar el valor."""
    return hashlib.sha256(texto.encode()).hexdigest()[:10]


def sesion_con_rol(rol_arn: str, region: str) -> boto3.Session:
    """Asume el rol de lectura con STS y devuelve una sesión con credenciales temporales."""
    base = boto3.Session(region_name=region, profile_name=os.getenv("AWS_PROFILE") or None)
    cred = base.client("sts").assume_role(RoleArn=rol_arn,
                                          RoleSessionName="lector-secreto-taller",
                                          DurationSeconds=900)["Credentials"]
    return boto3.Session(aws_access_key_id=cred["AccessKeyId"],
                         aws_secret_access_key=cred["SecretAccessKey"],
                         aws_session_token=cred["SessionToken"], region_name=region)


class LectorSecretos:
    """Lee secretos JSON; con ttl_segundos > 0 los guarda en memoria ese tiempo."""

    def __init__(self, sesion: boto3.Session, ttl_segundos: int = 0):
        self._cli = sesion.client("secretsmanager")
        self._ttl = ttl_segundos
        self._cache: dict[str, tuple[float, dict]] = {}
        self.llamadas_api = 0
        self.ultima_respuesta: dict = {}

    def obtener(self, nombre: str) -> dict:
        ahora = time.monotonic()
        if self._ttl and nombre in self._cache and ahora - self._cache[nombre][0] < self._ttl:
            return self._cache[nombre][1]
        r = self._cli.get_secret_value(SecretId=nombre)  # VersionStage=AWSCURRENT por defecto
        self.llamadas_api += 1
        self.ultima_respuesta = {k: r[k] for k in ("VersionId", "VersionStages", "CreatedDate")}
        valor = json.loads(r["SecretString"])
        self._cache[nombre] = (ahora, valor)
        return valor


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("secreto")
    ap.add_argument("--rol", help="ARN del rol de lectura (si se omite usa el perfil actual)")
    ap.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    a = ap.parse_args()
    ses = sesion_con_rol(a.rol, a.region) if a.rol else boto3.Session(region_name=a.region)
    lector = LectorSecretos(ses)
    v = lector.obtener(a.secreto)
    print(f"usuario={v['username']} password=({len(v['password'])} caracteres, "
          f"huella {huella(v['password'])}) versión={lector.ultima_respuesta['VersionId']}")
