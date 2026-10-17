"""Utilidades compartidas por todos los puntos del taller.

- Configuración común (región, prefijo de nombres).
- Clase Evidencia: guarda automáticamente en evidencias/puntoN/ cada paso
  ejecutado (JSON + log en Markdown + tablas CSV), para armar luego el
  documento de evidencias.
- Funciones de ayuda: id de cuenta, IP pública, esperas, vaciado de buckets.

Nunca se escriben valores de secretos en la evidencia: la función `_limpiar`
oculta cualquier clave que parezca una credencial.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable

import boto3

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
PREFIJO = os.getenv("TALLER_PREFIJO", "taller-ingdata")

_CLAVES_SENSIBLES = {
    "password", "secretstring", "secretbinary", "secretaccesskey",
    "sessiontoken", "accesskeyid", "masteruserpassword", "adminuserpassword",
}


def sesion() -> boto3.Session:
    """Sesión de boto3 en la región del taller (usa el perfil/credenciales activos)."""
    return boto3.Session(region_name=REGION, profile_name=os.getenv("AWS_PROFILE") or None)


def cliente(servicio: str, **kw):
    return sesion().client(servicio, **kw)


def id_cuenta() -> str:
    return cliente("sts").get_caller_identity()["Account"]


def identidad() -> dict:
    ident = cliente("sts").get_caller_identity()
    ident.pop("ResponseMetadata", None)
    return ident


def mi_ip_publica() -> str:
    with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10) as r:
        return r.read().decode().strip()


def ahora() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _serializar(o: Any):
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, bytes):
        return "<bytes>"
    try:
        from decimal import Decimal
        if isinstance(o, Decimal):
            return float(o)
    except ImportError:  # pragma: no cover
        pass
    return str(o)


def _limpiar(o: Any) -> Any:
    """Quita ResponseMetadata y oculta valores sensibles antes de guardarlos."""
    if isinstance(o, dict):
        res = {}
        for k, v in o.items():
            if k == "ResponseMetadata":
                continue
            if k.lower().replace("_", "") in _CLAVES_SENSIBLES:
                res[k] = "***OCULTO***"
            else:
                res[k] = _limpiar(v)
        return res
    if isinstance(o, list):
        return [_limpiar(x) for x in o]
    return o


class Evidencia:
    """Registra cada paso de un punto en evidencias/<punto>/."""

    def __init__(self, punto: str):
        self.punto = punto
        self.dir = RAIZ / "evidencias" / punto
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log = self.dir / "log.md"
        self._n = len(list(self.dir.glob("[0-9][0-9]_*.json")))
        if not self.log.exists():
            self.log.write_text(f"# Evidencias {punto}\n\n", encoding="utf-8")

    def _escribir_log(self, texto: str) -> None:
        with self.log.open("a", encoding="utf-8") as f:
            f.write(texto + "\n")

    def titulo(self, texto: str) -> None:
        print(f"\n=== {texto} ===")
        self._escribir_log(f"\n## {texto}  \n_{ahora()}_\n")

    def nota(self, texto: str) -> None:
        print(f"  - {texto}")
        self._escribir_log(f"- {texto}")

    def paso(self, nombre: str, datos: Any, mostrar: bool = True) -> Path:
        """Guarda la respuesta de una llamada como JSON numerado."""
        self._n += 1
        archivo = self.dir / f"{self._n:02d}_{nombre}.json"
        limpio = _limpiar(datos)
        archivo.write_text(json.dumps(limpio, indent=2, ensure_ascii=False, default=_serializar),
                           encoding="utf-8")
        if mostrar:
            print(f"  [evidencia] {archivo.name}")
        self._escribir_log(f"- Evidencia: `{archivo.name}` ({ahora()})")
        return archivo

    def tabla(self, nombre: str, columnas: list[str], filas: Iterable[Iterable[Any]],
              descripcion: str = "") -> Path:
        """Guarda resultados tabulares como CSV y los agrega al log en Markdown."""
        filas = [list(f) for f in filas]
        archivo = self.dir / f"{nombre}.csv"
        with archivo.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(columnas)
            w.writerows(filas)
        md = [f"\n**{nombre}** {('- ' + descripcion) if descripcion else ''}\n",
              "| " + " | ".join(columnas) + " |",
              "|" + "---|" * len(columnas)]
        for fila in filas[:50]:
            md.append("| " + " | ".join("" if v is None else str(v) for v in fila) + " |")
        if len(filas) > 50:
            md.append(f"\n_({len(filas)} filas; ver {archivo.name})_")
        self._escribir_log("\n".join(md) + "\n")
        print(f"  [tabla] {archivo.name} ({len(filas)} filas)")
        for fila in filas[:10]:
            print("    ", fila)
        return archivo

    def texto(self, nombre: str, contenido: str) -> Path:
        archivo = self.dir / nombre
        archivo.write_text(contenido, encoding="utf-8")
        self._escribir_log(f"- Archivo: `{nombre}`")
        print(f"  [archivo] {nombre}")
        return archivo


class Estado:
    """Guarda identificadores de recursos creados (para poder limpiarlos después)."""

    def __init__(self, punto: str):
        self.archivo = RAIZ / ".estado" / f"{punto}.json"
        self.archivo.parent.mkdir(exist_ok=True)
        self.datos = json.loads(self.archivo.read_text()) if self.archivo.exists() else {}

    def __getitem__(self, k):
        return self.datos[k]

    def get(self, k, default=None):
        return self.datos.get(k, default)

    def __setitem__(self, k, v):
        self.datos[k] = v
        self.archivo.write_text(json.dumps(self.datos, indent=2, default=_serializar))

    def borrar(self):
        if self.archivo.exists():
            self.archivo.unlink()
        self.datos = {}


def esperar(condicion: Callable[[], Any], descripcion: str, intervalo: int = 15,
            maximo: int = 3600) -> Any:
    """Llama a `condicion` hasta que devuelva algo verdadero (o se agote el tiempo)."""
    inicio = time.time()
    while True:
        res = condicion()
        if res:
            print(f"  ✓ {descripcion} ({int(time.time() - inicio)} s)")
            return res
        if time.time() - inicio > maximo:
            raise TimeoutError(f"Tiempo agotado esperando: {descripcion}")
        print(f"  … esperando {descripcion} ({int(time.time() - inicio)} s)")
        time.sleep(intervalo)


def vaciar_y_borrar_bucket(nombre: str) -> None:
    s3 = sesion().resource("s3")
    bucket = s3.Bucket(nombre)
    try:
        bucket.object_versions.delete()
        bucket.objects.all().delete()
        bucket.delete()
    except s3.meta.client.exceptions.NoSuchBucket:
        pass


def crear_bucket(nombre: str) -> None:
    s3 = cliente("s3")
    try:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=nombre)
        else:
            s3.create_bucket(Bucket=nombre,
                             CreateBucketConfiguration={"LocationConstraint": REGION})
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    s3.put_public_access_block(
        Bucket=nombre,
        PublicAccessBlockConfiguration={k: True for k in (
            "BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")},
    )


def bucket_existe(nombre: str) -> bool:
    try:
        cliente("s3").head_bucket(Bucket=nombre)
        return True
    except Exception:
        return False


def crear_rol_servicio(nombre: str, principales: list[str], politicas_administradas: list[str],
                       politica_en_linea: dict | None = None, descripcion: str = "") -> str:
    """Crea (o reutiliza) un rol de IAM que puede asumir un servicio de AWS."""
    iam = cliente("iam")
    confianza = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": principales},
                       "Action": "sts:AssumeRole"}],
    }
    try:
        arn = iam.create_role(RoleName=nombre, AssumeRolePolicyDocument=json.dumps(confianza),
                              Description=descripcion,
                              Tags=[{"Key": "proyecto", "Value": PREFIJO}])["Role"]["Arn"]
        nuevo = True
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=nombre)["Role"]["Arn"]
        nuevo = False
    for p in politicas_administradas:
        iam.attach_role_policy(RoleName=nombre, PolicyArn=p)
    if politica_en_linea:
        iam.put_role_policy(RoleName=nombre, PolicyName=f"{nombre}-inline",
                            PolicyDocument=json.dumps(politica_en_linea))
    if nuevo:
        print("  … esperando propagación del rol en IAM (15 s)")
        time.sleep(15)
    return arn


def borrar_rol(nombre: str) -> None:
    iam = cliente("iam")
    try:
        for p in iam.list_attached_role_policies(RoleName=nombre)["AttachedPolicies"]:
            iam.detach_role_policy(RoleName=nombre, PolicyArn=p["PolicyArn"])
        for p in iam.list_role_policies(RoleName=nombre)["PolicyNames"]:
            iam.delete_role_policy(RoleName=nombre, PolicyName=p)
        iam.delete_role(RoleName=nombre)
    except iam.exceptions.NoSuchEntityException:
        pass


def rol_existe(nombre: str) -> bool:
    try:
        cliente("iam").get_role(RoleName=nombre)
        return True
    except Exception:
        return False


def vpc_por_defecto() -> tuple[str, list[dict]]:
    """Devuelve (vpc_id, subredes) de la VPC por defecto de la región."""
    ec2 = cliente("ec2")
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        raise RuntimeError("No hay VPC por defecto en la región. Cree una con "
                           "'aws ec2 create-default-vpc' o ajuste el script.")
    vpc_id = vpcs[0]["VpcId"]
    subredes = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"]
    subredes.sort(key=lambda s: s["AvailabilityZone"])
    return vpc_id, subredes
