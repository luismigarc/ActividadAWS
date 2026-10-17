"""Consulta de precios con la AWS Price List API (boto3 'pricing').

Permite que la estimación de costos de cada punto use precios reales de la
región en lugar de valores copiados a mano. Si la API no responde (falta de
permiso pricing:GetProducts, por ejemplo) se usan valores de referencia que
deben verificarse en https://calculator.aws.
"""
from __future__ import annotations

import json

from comun.utilidades import REGION, sesion

# Valores de referencia para us-east-1 (USD). Verificar en calculator.aws.
REFERENCIA = {
    "secrets_mes": 0.40,              # por secreto al mes (prorrateado por hora)
    "secrets_10k_llamadas": 0.05,     # por cada 10.000 llamadas a la API
    "s3_gb_mes": 0.023,               # S3 Standard
    "s3_put_1000": 0.005,
    "s3_get_1000": 0.0004,
    "glue_dpu_hora": 0.44,            # crawler: por DPU-hora, por segundo, mínimo 10 min
    "glue_catalogo_objetos_gratis": 1_000_000,
    "glue_catalogo_100k_objetos_mes": 1.00,
    "glue_catalogo_millon_solicitudes": 1.00,
    "athena_tb": 5.00,                # por TB escaneado, mínimo 10 MB por consulta
    "redshift_rpu_hora": 0.375,       # Serverless, por segundo con mínimo de 60 s
    "redshift_rms_gb_mes": 0.024,     # almacenamiento administrado
    "neptune_ncu_hora": 0.1608,       # Serverless (mínimo 1 NCU)
    "neptune_gb_mes": 0.10,
    "neptune_millon_io": 0.20,
    "neptune_backup_gb_mes": 0.021,
}


def _region_pricing():
    # La API de precios solo existe en algunas regiones; us-east-1 siempre funciona.
    return sesion().client("pricing", region_name="us-east-1")


def buscar_precios(servicio: str, palabras: list[str], filtros: dict | None = None,
                   max_paginas: int = 15, limite: int = 12) -> list[dict]:
    """Busca dimensiones de precio On-Demand cuya descripción contenga todas las palabras."""
    cli = _region_pricing()
    f = [{"Type": "TERM_MATCH", "Field": "regionCode", "Value": REGION}]
    for k, v in (filtros or {}).items():
        f.append({"Type": "TERM_MATCH", "Field": k, "Value": v})
    encontrados: list[dict] = []
    token = None
    for _ in range(max_paginas):
        kw = {"ServiceCode": servicio, "Filters": f, "FormatVersion": "aws_v1", "MaxResults": 100}
        if token:
            kw["NextToken"] = token
        resp = cli.get_products(**kw)
        for item in resp["PriceList"]:
            prod = json.loads(item)
            for term in prod.get("terms", {}).get("OnDemand", {}).values():
                for dim in term["priceDimensions"].values():
                    desc = dim.get("description", "")
                    if all(p.lower() in desc.lower() for p in palabras):
                        encontrados.append({
                            "descripcion": desc,
                            "unidad": dim.get("unit"),
                            "usd": float(dim["pricePerUnit"].get("USD", 0)),
                            "usagetype": prod.get("product", {}).get("attributes", {}).get("usagetype"),
                        })
        token = resp.get("NextToken")
        if not token or len(encontrados) >= limite:
            break
    # quitar duplicados
    vistos, unicos = set(), []
    for e in encontrados:
        if e["descripcion"] not in vistos:
            vistos.add(e["descripcion"])
            unicos.append(e)
    return unicos[:limite]


def consultar_seguro(servicio: str, palabras: list[str], filtros: dict | None = None) -> list[dict]:
    try:
        return buscar_precios(servicio, palabras, filtros)
    except Exception as e:  # sin permisos o sin red
        return [{"error": f"{type(e).__name__}: {e}",
                 "nota": "Se usarán valores de referencia (comun/precios.py::REFERENCIA)"}]
