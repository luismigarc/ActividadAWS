"""Ejecuta las mismas consultas del punto 5 sobre SQLite (local, sin AWS).

Sirve para conocer de antemano los resultados esperados y compararlos con los
que devuelve Redshift. Uso: uv run python punto5_redshift/verificar_local.py
"""
import csv
import sqlite3
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def leer_consultas() -> list[dict]:
    """Separa 03_consultas.sql en bloques {nombre, pregunta, sql}."""
    consultas, actual = [], None
    for linea in (AQUI / "sql" / "03_consultas.sql").read_text(encoding="utf-8").splitlines():
        if linea.startswith("-- name:"):
            actual = {"nombre": linea.split(":", 1)[1].strip(), "pregunta": "", "sql": ""}
            consultas.append(actual)
        elif linea.startswith("-- pregunta:") and actual:
            actual["pregunta"] = linea.split(":", 1)[1].strip()
        elif actual is not None:
            actual["sql"] += linea + "\n"
    for c in consultas:
        c["sql"] = c["sql"].strip().rstrip(";")
    return consultas


def main():
    db = sqlite3.connect(":memory:")
    for tabla in ("clientes", "productos", "pedidos"):
        with (AQUI / "datos" / f"{tabla}.csv").open(encoding="utf-8") as f:
            filas = list(csv.reader(f))
        cols = filas[0]
        db.execute(f"CREATE TABLE {tabla} ({', '.join(cols)})")
        convertidas = [[float(v) if v.replace('.', '', 1).isdigit() else v for v in fila]
                       for fila in filas[1:]]
        db.executemany(f"INSERT INTO {tabla} VALUES ({', '.join('?' * len(cols))})", convertidas)
    salida = AQUI / "resultados_esperados"
    salida.mkdir(exist_ok=True)
    for c in leer_consultas():
        cur = db.execute(c["sql"])
        cols = [d[0] for d in cur.description]
        filas = cur.fetchall()
        with (salida / f"{c['nombre']}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(filas)
        print(f"\n{c['nombre']}: {c['pregunta']}\n{cols}")
        for fila in filas:
            print("  ", fila)


if __name__ == "__main__":
    main()
