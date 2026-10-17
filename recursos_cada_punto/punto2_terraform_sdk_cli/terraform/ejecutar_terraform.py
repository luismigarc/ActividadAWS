"""Ejecuta Terraform (init/plan/apply y destroy) guardando la salida como evidencia.

    export AWS_PROFILE=user_cli
    uv run python punto2_terraform_sdk_cli/terraform/ejecutar_terraform.py crear
    uv run python punto2_terraform_sdk_cli/terraform/ejecutar_terraform.py eliminar

También revisa el archivo de estado (terraform.tfstate) para confirmar que no contiene
contraseñas: con manage_master_user_password=true solo guarda el ARN del secreto.
El estado NUNCA se sube al repositorio (.gitignore).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI.parents[1]))

from comun.utilidades import Evidencia, identidad  # noqa: E402
from comun_p2 import registrar_tiempo, verificar_recursos  # noqa: E402

EV = Evidencia("punto2")
PREFIJO = "taller-ingdata-p2-tf"
SALIDAS = EV.dir / "terraform"
SALIDAS.mkdir(exist_ok=True)


def tf(*args: str, archivo: str | None = None) -> str:
    cmd = ["terraform", *args]
    print(f"$ {' '.join(cmd)}")
    env = {**os.environ, "TF_IN_AUTOMATION": "1", "TF_VAR_perfil_aws":
           os.getenv("AWS_PROFILE", "user_cli"),
           "TF_VAR_region": os.getenv("AWS_REGION", "us-east-1")}
    r = subprocess.run(cmd, cwd=AQUI, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    salida = r.stdout + ("\n" + r.stderr if r.stderr else "")
    print(salida[-3000:])
    if archivo:
        (SALIDAS / archivo).write_text(f"$ {' '.join(cmd)}\n\n{salida}", encoding="utf-8")
        EV.nota(f"Salida guardada: terraform/{archivo}")
    if r.returncode != 0:
        raise SystemExit(f"terraform {args[0]} falló (código {r.returncode})")
    return r.stdout


def revisar_estado() -> None:
    estado = AQUI / "terraform.tfstate"
    if not estado.exists():
        return
    texto = estado.read_text(encoding="utf-8")
    datos = json.loads(texto)
    claves = sorted(set(re.findall(r'"([a-z_]*password[a-z_]*)"\s*:', texto)))
    hallazgos = []
    for res in datos.get("resources", []):
        for inst in res.get("instances", []):
            atr = inst.get("attributes", {})
            for k in claves:
                if k in atr:
                    v = atr[k]
                    hallazgos.append([f"{res['type']}.{res['name']}", k,
                                      "vacío/nulo" if v in (None, "", False) else
                                      ("true" if v is True else "¡CONTIENE VALOR!")])
    EV.tabla("terraform_estado_contrasenas", ["recurso", "atributo", "valor"], hallazgos,
             "Atributos *password* en terraform.tfstate (manage_master_user_password=true)")
    secretos = [inst["attributes"].get("master_user_secret") for res in datos["resources"]
                if res["type"] == "aws_db_instance" for inst in res["instances"]]
    EV.paso("terraform_estado_master_user_secret", secretos)
    EV.nota("El estado guarda IDs, ARN, endpoints y atributos de cada recurso; aquí solo el ARN "
            "del secreto de RDS, no la contraseña.")


def crear() -> None:
    EV.titulo("Versión Terraform - creación")
    EV.paso("tf_identidad", identidad())
    t0 = time.time()
    tf("version", archivo="00_version.txt")
    tf("init", "-input=false", "-no-color", archivo="01_init.txt")
    tf("validate", "-no-color", archivo="02_validate.txt")
    tf("plan", "-input=false", "-no-color", "-out=plan.tfplan", archivo="03_plan.txt")
    tf("apply", "-input=false", "-no-color", "plan.tfplan", archivo="04_apply.txt")
    seg = time.time() - t0
    registrar_tiempo("terraform", "crear", seg)
    tf("output", "-json", archivo="05_output.json")
    tf("state", "list", archivo="06_state_list.txt")
    revisar_estado()
    (AQUI / "plan.tfplan").unlink(missing_ok=True)
    EV.nota(f"Tiempo de creación con Terraform: {seg:.0f} s")


def eliminar() -> None:
    EV.titulo("Versión Terraform - eliminación")
    try:
        secreto = json.loads(tf("output", "-json"))["rds_secreto_arn"]["value"]
    except Exception:  # noqa: BLE001
        secreto = None
    t0 = time.time()
    tf("plan", "-destroy", "-input=false", "-no-color", archivo="07_plan_destroy.txt")
    tf("destroy", "-auto-approve", "-input=false", "-no-color", archivo="08_destroy.txt")
    registrar_tiempo("terraform", "eliminar", time.time() - t0)
    tf("state", "list", archivo="09_state_list_vacio.txt")
    EV.tabla("tf_verificacion_eliminacion", ["recurso", "estado"],
             verificar_recursos(PREFIJO, secreto))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["crear", "eliminar"])
    {"crear": crear, "eliminar": eliminar}[ap.parse_args().accion]()
