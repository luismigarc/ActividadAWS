"""Compara los tres métodos (tiempos medidos) y estima los costos del punto 2.

    uv run python punto2_terraform_sdk_cli/comparar_y_costos.py
"""
from __future__ import annotations

import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from comun.precios import REFERENCIA, consultar_seguro  # noqa: E402
from comun.utilidades import Evidencia  # noqa: E402
from comun_p2 import CLASE_RDS, TIEMPOS, TIPO_EC2  # noqa: E402

EV = Evidencia("punto2")

REF = {"ec2_h": 0.0104, "rds_h": 0.016, "ebs_gp3_gb_mes": 0.08, "rds_gp3_gb_mes": 0.115,
       "ipv4_h": 0.005}


def primer_precio(lista, defecto):
    for p in lista:
        if p.get("usd"):
            return p["usd"]
    return defecto


def main():
    EV.titulo("Comparación de métodos y costos")
    if TIEMPOS.exists():
        with TIEMPOS.open(encoding="utf-8") as f:
            filas = [[r["metodo"], r["accion"], r["segundos"]] for r in csv.DictReader(f)]
        EV.tabla("tiempos_medidos", ["metodo", "accion", "segundos"], filas,
                 "Tiempos reales de creación y eliminación por método")
    EV.tabla("comparacion_metodos", ["criterio", "Terraform", "Boto3 (SDK)", "AWS CLI"], [
        ["Estilo", "Declarativo: describe el estado deseado", "Imperativo: código Python",
         "Imperativo: comandos sueltos / script"],
        ["Estado", "Archivo tfstate: sabe qué creó y calcula diferencias",
         "Hay que guardar IDs a mano (.estado/)", "Hay que guardar IDs a mano"],
        ["Plan previo", "terraform plan muestra los cambios antes de aplicarlos", "No", "No"],
        ["Dependencias y orden", "Automáticas (grafo de recursos)", "Manuales (waiters)",
         "Manuales (aws ... wait)"],
        ["Eliminación", "terraform destroy en orden inverso", "Código propio en orden inverso",
         "Comandos en orden inverso"],
        ["Idempotencia", "Sí (reaplicar no duplica)", "Solo si se programa", "No"],
        ["Mejor para", "Infraestructura reproducible y versionada",
         "Automatización con lógica, integración en aplicaciones",
         "Tareas rápidas, pruebas puntuales, scripts cortos"],
    ], "Comparación cualitativa")

    ec2 = primer_precio(consultar_seguro("AmazonEC2", [TIPO_EC2], {
        "instanceType": TIPO_EC2, "operatingSystem": "Linux", "tenancy": "Shared",
        "preInstalledSw": "NA", "capacitystatus": "Used"}), REF["ec2_h"])
    rds = primer_precio(consultar_seguro("AmazonRDS", [CLASE_RDS], {
        "instanceType": CLASE_RDS, "databaseEngine": "PostgreSQL",
        "deploymentOption": "Single-AZ"}), REF["rds_h"])
    ebs_h = 8 * REF["ebs_gp3_gb_mes"] / 730
    rds_alm_h = 20 * REF["rds_gp3_gb_mes"] / 730
    sec_h = REFERENCIA["secrets_mes"] / 730
    total_h = ec2 + rds + ebs_h + rds_alm_h + sec_h
    filas = [
        [f"EC2 {TIPO_EC2}", f"{ec2:.4f}/h", f"{ec2:.4f}", f"{ec2 * 168:.2f}"],
        ["EBS gp3 8 GB (disco de la EC2)", f"{REF['ebs_gp3_gb_mes']}/GB-mes", f"{ebs_h:.4f}",
         f"{ebs_h * 168:.2f}"],
        [f"RDS PostgreSQL {CLASE_RDS} Single-AZ", f"{rds:.4f}/h", f"{rds:.4f}", f"{rds * 168:.2f}"],
        ["Almacenamiento RDS gp3 20 GB", f"{REF['rds_gp3_gb_mes']}/GB-mes", f"{rds_alm_h:.4f}",
         f"{rds_alm_h * 168:.2f}"],
        ["Secreto de RDS (Secrets Manager)", f"{REFERENCIA['secrets_mes']}/mes", f"{sec_h:.5f}",
         f"{sec_h * 168:.3f}"],
        ["Bucket S3 vacío", "0,023/GB-mes", "0.0000", "0.00"],
        ["IPv4 pública (no se usa: evitada)", f"{REF['ipv4_h']}/h", "0", "0"],
        ["TOTAL", "", f"{total_h:.4f}", f"{total_h * 168:.2f}"],
    ]
    EV.tabla("estimacion_costos", ["componente", "precio_USD", "1_hora_USD", "1_semana_USD"],
             filas, "us-east-1, sin capa gratuita. Con capa gratuita (cuentas elegibles) EC2, "
                    "RDS y 20-30 GB de almacenamiento pueden salir en 0.")


if __name__ == "__main__":
    main()
