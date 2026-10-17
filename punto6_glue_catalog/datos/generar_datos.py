"""Genera los CSV de ventas del punto 6 (semilla fija => siempre los mismos datos)."""
import csv
import random
from pathlib import Path

AQUI = Path(__file__).parent
CIUDADES = {"Medellin": "050021", "Bogota": "110111", "Cali": "760001",
            "Barranquilla": "080001", "Envigado": "055420"}
PRODUCTOS = [("Portatil", "Tecnologia", 3499.90), ("Mouse", "Tecnologia", 59.90),
             ("Monitor", "Tecnologia", 899.50), ("Silla", "Muebles", 649.00),
             ("Escritorio", "Muebles", 1199.99), ("Cuaderno", "Papeleria", 12.50),
             ("Lapicero", "Papeleria", 3.20), ("Audifonos", "Tecnologia", 249.00)]
COLUMNAS = ["id_venta", "fecha", "ciudad", "codigo_postal", "producto", "categoria",
            "cantidad", "precio_unitario", "cliente_vip"]


def generar(nombre, inicio_id, n, mes, semilla):
    rnd = random.Random(semilla)
    filas = []
    for i in range(n):
        ciudad = rnd.choice(list(CIUDADES))
        prod, cat, precio = rnd.choice(PRODUCTOS)
        filas.append([inicio_id + i, f"{mes}-{rnd.randint(1, 28):02d}", ciudad, CIUDADES[ciudad],
                      prod, cat, rnd.randint(1, 5), f"{precio:.2f}",
                      "true" if rnd.random() < 0.3 else "false"])
    filas.sort(key=lambda f: f[1])
    with (AQUI / nombre).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS)
        w.writerows(filas)
    print(f"{nombre}: {n} registros")


if __name__ == "__main__":
    generar("ventas_2026-09.csv", 1, 25, "2026-09", 6)
    generar("ventas_2026-10.csv", 26, 10, "2026-10", 66)
