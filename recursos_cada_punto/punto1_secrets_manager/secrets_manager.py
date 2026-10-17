"""Punto 1 - AWS Secrets Manager.

Uso (desde la raíz del repositorio):
    uv run python punto1_secrets_manager/secrets_manager.py todo
    uv run python punto1_secrets_manager/secrets_manager.py limpiar

Pasos: crear | permisos | leer | actualizar | cache | costos | limpiar

1. crear      -> secreto de prueba `taller/punto1/db-ficticia` con usuario y contraseña
                 ficticios (la contraseña la genera Secrets Manager: get_random_password).
                 También crea un secreto de "control" que el programa NO debe poder leer.
2. permisos   -> rol IAM `taller-ingdata-p1-lector` con una política que solo permite
                 GetSecretValue/DescribeSecret sobre el ARN de ESE secreto.
3. leer       -> ejecuta lector_secreto.py con el rol (STS AssumeRole) y comprueba que lee
                 el secreto de prueba y que se le niega el secreto de control.
4. actualizar -> put_secret_value cambia el valor (nueva versión AWSCURRENT) y el mismo
                 programa, sin cambiar código, obtiene la versión nueva.
5. cache      -> compara llamadas a la API con y sin caché en memoria.
6. costos     -> estimación de costos.
7. limpiar    -> elimina los secretos (sin ventana de recuperación) y el rol, y verifica.

Nunca se imprime ni se guarda la contraseña: solo su longitud y una huella SHA-256 corta.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from botocore.exceptions import ClientError  # noqa: E402

from comun.precios import REFERENCIA, consultar_seguro  # noqa: E402
from comun.utilidades import (PREFIJO, REGION, Estado, Evidencia, borrar_rol,  # noqa: E402
                              cliente, id_cuenta, identidad, rol_existe)
from puntos.punto1_secrets_manager.lector_secreto import (LectorSecretos, huella,  # noqa: E402
                                                   sesion_con_rol)

EV = Evidencia("punto1")
ESTADO = Estado("punto1")
SECRETO = "taller/punto1/db-ficticia"
SECRETO_CONTROL = "taller/punto1/otro-secreto"
ROL = f"{PREFIJO}-p1-lector"


def _nuevo_valor() -> str:
    sm = cliente("secretsmanager")
    pwd = sm.get_random_password(PasswordLength=20, ExcludePunctuation=True)["RandomPassword"]
    return json.dumps({"username": "usuario_ficticio", "password": pwd,
                       "engine": "postgres", "host": "db.ejemplo.local", "port": 5432})


def crear() -> None:
    EV.titulo("Paso 1 - Crear el secreto de prueba")
    EV.paso("identidad_usada", identidad())
    sm = cliente("secretsmanager")
    for nombre, desc in ((SECRETO, "Credenciales FICTICIAS del taller (punto 1)"),
                         (SECRETO_CONTROL, "Secreto de control: el lector NO debe poder leerlo")):
        try:
            r = sm.create_secret(Name=nombre, Description=desc, SecretString=_nuevo_valor(),
                                 Tags=[{"Key": "proyecto", "Value": PREFIJO}])
            EV.nota(f"Creado {nombre} -> versión {r['VersionId']}")
        except sm.exceptions.ResourceExistsException:
            EV.nota(f"{nombre} ya existía")
    d = sm.describe_secret(SecretId=SECRETO)
    ESTADO["secreto_arn"] = d["ARN"]
    ESTADO["control_arn"] = sm.describe_secret(SecretId=SECRETO_CONTROL)["ARN"]
    EV.paso("secreto_metadatos", d)   # solo metadatos; nunca SecretString


def politica_lector(arn: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "LeerSoloElSecretoDelTaller",
            "Effect": "Allow",
            "Action": ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"],
            "Resource": arn,  # ARN completo (incluye el sufijo aleatorio de 6 caracteres)
        }],
    }


def permisos() -> None:
    EV.titulo("Paso 2 - Permisos de mínimo privilegio para el programa")
    iam = cliente("iam")
    ident = identidad()
    # Quién puede asumir el rol: el usuario actual (si es un usuario IAM) o la cuenta.
    principal = ident["Arn"] if ":user/" in ident["Arn"] else f"arn:aws:iam::{id_cuenta()}:root"
    confianza = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"AWS": principal}, "Action": "sts:AssumeRole"}]}
    politica = politica_lector(ESTADO["secreto_arn"])
    try:
        iam.create_role(RoleName=ROL, AssumeRolePolicyDocument=json.dumps(confianza),
                        Description="Programa Python que solo lee el secreto del punto 1",
                        MaxSessionDuration=3600)
        time.sleep(10)
    except iam.exceptions.EntityAlreadyExistsException:
        pass
    iam.put_role_policy(RoleName=ROL, PolicyName="leer-solo-secreto-punto1",
                        PolicyDocument=json.dumps(politica))
    ESTADO["rol_arn"] = iam.get_role(RoleName=ROL)["Role"]["Arn"]
    (pathlib.Path(__file__).parent / "politica_lector.json").write_text(
        json.dumps(politica_lector("arn:aws:secretsmanager:<region>:<cuenta>:secret:"
                                   "taller/punto1/db-ficticia-XXXXXX"), indent=2))
    EV.texto("politica_acceso.json", json.dumps(politica, indent=2))
    EV.texto("politica_confianza.json", json.dumps(confianza, indent=2))
    EV.nota(f"Rol {ROL}: solo GetSecretValue/DescribeSecret sobre {ESTADO['secreto_arn']}")
    # Simulación de política: comprueba permitido/denegado sin ejecutar nada
    filas = []
    for recurso, arn in (("secreto de prueba", ESTADO["secreto_arn"]),
                         ("secreto de control", ESTADO["control_arn"])):
        try:
            sim = iam.simulate_principal_policy(
                PolicySourceArn=ESTADO["rol_arn"],
                ActionNames=["secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue",
                             "secretsmanager:DeleteSecret"], ResourceArns=[arn])
            filas += [[r["EvalActionName"], recurso, r["EvalDecision"]]
                      for r in sim["EvaluationResults"]]
        except Exception as e:  # noqa: BLE001
            EV.nota(f"No se pudo simular la política: {e}")
    EV.tabla("simulacion_politica", ["accion", "recurso", "decision"], filas,
             "IAM Policy Simulator sobre el rol del lector")
    print("  … esperando propagación de IAM (10 s)")
    time.sleep(10)


def _leer_con_rol(etiqueta: str) -> dict:
    lector = LectorSecretos(sesion_con_rol(ESTADO["rol_arn"], REGION), ttl_segundos=0)
    valor = lector.obtener(SECRETO)
    meta = lector.ultima_respuesta
    info = {"usuario": valor["username"], "longitud_password": len(valor["password"]),
            "huella_sha256": huella(valor["password"]), "VersionId": meta["VersionId"],
            "VersionStages": meta["VersionStages"], "CreatedDate": meta["CreatedDate"]}
    EV.paso(f"lectura_{etiqueta}", info)
    EV.nota(f"[{etiqueta}] versión {meta['VersionId'][:8]}… etapas {meta['VersionStages']} "
            f"huella {info['huella_sha256']}")
    return info


def leer() -> None:
    EV.titulo("Paso 3 - Lectura desde Python con Boto3 (rol de mínimo privilegio)")
    ESTADO["lectura_inicial"] = _leer_con_rol("inicial")
    try:
        LectorSecretos(sesion_con_rol(ESTADO["rol_arn"], REGION)).obtener(SECRETO_CONTROL)
        EV.nota("ALERTA: el rol pudo leer el secreto de control")
    except ClientError as e:
        EV.nota(f"Secreto de control denegado correctamente: {e.response['Error']['Code']}")
        EV.paso("acceso_denegado_control", {"error": e.response["Error"]})


def actualizar() -> None:
    EV.titulo("Paso 4 - Actualizar el valor y volver a leer sin cambiar el código")
    sm = cliente("secretsmanager")
    r = sm.put_secret_value(SecretId=SECRETO, SecretString=_nuevo_valor())
    EV.nota(f"put_secret_value -> nueva versión {r['VersionId']} con etapas {r['VersionStages']}")
    nueva = _leer_con_rol("despues_de_actualizar")
    ini = ESTADO.get("lectura_inicial", {})
    EV.tabla("comparacion_versiones", ["momento", "VersionId", "etapas", "huella_password"],
             [["antes", ini.get("VersionId"), ini.get("VersionStages"), ini.get("huella_sha256")],
              ["después", nueva["VersionId"], nueva["VersionStages"], nueva["huella_sha256"]]],
             "El programa obtiene AWSCURRENT, que ahora apunta a la versión nueva")
    vers = sm.list_secret_version_ids(SecretId=SECRETO)["Versions"]
    EV.tabla("versiones_del_secreto", ["VersionId", "etapas", "creada"],
             [[v["VersionId"], v.get("VersionStages"), v.get("CreatedDate")] for v in vers])


def cache() -> None:
    EV.titulo("Paso 5 - Llamadas repetidas: sin caché vs caché en memoria")
    ses = sesion_con_rol(ESTADO["rol_arn"], REGION)
    sin = LectorSecretos(ses, ttl_segundos=0)
    con = LectorSecretos(ses, ttl_segundos=300)
    n = 50
    t0 = time.time()
    for _ in range(n):
        sin.obtener(SECRETO)
    t_sin = time.time() - t0
    t0 = time.time()
    for _ in range(n):
        con.obtener(SECRETO)
    t_con = time.time() - t0
    EV.tabla("comparacion_cache", ["modo", "lecturas", "llamadas_API", "tiempo_s"],
             [["sin caché", n, sin.llamadas_api, round(t_sin, 2)],
              ["caché TTL 300 s", n, con.llamadas_api, round(t_con, 2)]],
             "Cada GetSecretValue se cobra: la caché reduce costo y latencia")


def costos() -> None:
    EV.titulo("Paso 6 - Costos")
    EV.paso("precios_api", consultar_seguro("AWSSecretsManager", []))
    s, c = REFERENCIA["secrets_mes"], REFERENCIA["secrets_10k_llamadas"]
    filas = [
        ["2 secretos de prueba ~1 hora", f"{s} USD/secreto-mes prorrateado",
         f"${2 * s / 730:.5f}"],
        ["~110 llamadas a la API en el taller", f"{c} USD por 10.000", f"${110 / 10000 * c:.6f}"],
        ["App que lee 1 vez/segundo sin caché (1 mes)", "2.592.000 llamadas",
         f"${2_592_000 / 10000 * c:.2f}/mes + ${s}"],
        ["Misma app con caché de 5 min", "8.640 llamadas", f"${8640 / 10000 * c:.4f}/mes + ${s}"],
    ]
    EV.tabla("estimacion_costos", ["escenario", "base", "costo_usd"], filas)


def limpiar() -> None:
    EV.titulo("Limpieza - eliminar secretos de prueba y rol")
    sm = cliente("secretsmanager")
    for nombre in (SECRETO, SECRETO_CONTROL):
        try:
            r = sm.delete_secret(SecretId=nombre, ForceDeleteWithoutRecovery=True)
            EV.nota(f"delete_secret {nombre} -> DeletionDate {r.get('DeletionDate')}")
        except sm.exceptions.ResourceNotFoundException:
            EV.nota(f"{nombre} no existía")
    borrar_rol(ROL)
    time.sleep(5)
    verif = []
    for nombre in (SECRETO, SECRETO_CONTROL):
        try:
            d = sm.describe_secret(SecretId=nombre)
            verif.append([nombre, f"pendiente de borrado {d.get('DeletedDate')}"])
        except sm.exceptions.ResourceNotFoundException:
            verif.append([nombre, "no existe (ResourceNotFoundException)"])
    verif.append([f"Rol {ROL}", "SIGUE EXISTIENDO" if rol_existe(ROL) else "no existe"])
    EV.tabla("verificacion_eliminacion", ["recurso", "estado"], verif)
    ESTADO.borrar()


PASOS = {"crear": crear, "permisos": permisos, "leer": leer, "actualizar": actualizar,
         "cache": cache, "costos": costos, "limpiar": limpiar}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("paso", choices=list(PASOS) + ["todo"])
    a = ap.parse_args()
    print(f"Región: {REGION}")
    if a.paso == "todo":
        for p in ("crear", "permisos", "leer", "actualizar", "cache", "costos"):
            PASOS[p]()
        print("\nListo. Luego: uv run python punto1_secrets_manager/secrets_manager.py limpiar")
    else:
        PASOS[a.paso]()
