"""Genera el conjunto de datos del punto 5 (semilla fija): clientes, productos, pedidos.

Relaciones: pedidos.id_cliente -> clientes.id_cliente
            pedidos.id_producto -> productos.id_producto
"""
import csv
import datetime as dt
import random
from pathlib import Path

AQUI = Path(__file__).parent
rnd = random.Random(2026)

NOMBRES = ["Ana", "Bruno", "Carla", "Diego", "Elena", "Felipe", "Gabriela", "Hector",
           "Isabel", "Julian", "Karen", "Luis", "Manuela", "Nicolas", "Olga", "Pablo",
           "Quintina", "Ricardo", "Sara", "Tomas"]
APELLIDOS = ["Gomez", "Rojas", "Perez", "Lopez", "Restrepo", "Mejia", "Cardona", "Vargas"]
CIUDADES = ["Medellin", "Medellin", "Bogota", "Cali", "Barranquilla", "Envigado"]
SEGMENTOS = ["Estandar", "Estandar", "Premium", "Corporativo"]
PRODUCTOS = [
    (1, "Portatil 14", "Tecnologia", 3499000), (2, "Mouse inalambrico", "Tecnologia", 89000),
    (3, "Monitor 27", "Tecnologia", 1290000), (4, "Silla ergonomica", "Muebles", 899000),
    (5, "Escritorio en L", "Muebles", 1150000), (6, "Lampara LED", "Hogar", 129000),
    (7, "Cafetera", "Hogar", 459000), (8, "Audifonos", "Tecnologia", 349000),
    (9, "Teclado mecanico", "Tecnologia", 420000), (10, "Estanteria", "Muebles", 510000),
]


def escribir(nombre, columnas, filas):
    with (AQUI / nombre).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(columnas)
        w.writerows(filas)
    print(f"{nombre}: {len(filas)} filas")


clientes = []
for i, n in enumerate(NOMBRES, start=1):
    fecha = dt.date(2025, 1, 1) + dt.timedelta(days=rnd.randint(0, 540))
    clientes.append([i, f"{n} {rnd.choice(APELLIDOS)}", rnd.choice(CIUDADES),
                     rnd.choice(SEGMENTOS), fecha.isoformat()])

pedidos = []
for i in range(1, 121):
    fecha = dt.date(2026, 4, 1) + dt.timedelta(days=rnd.randint(0, 182))
    prod = rnd.choice(PRODUCTOS)
    cant = rnd.choices([1, 2, 3, 4, 5], weights=[50, 25, 12, 8, 5])[0]
    desc = rnd.choice([0, 0, 0, 5, 10, 15])
    pedidos.append([1000 + i, rnd.randint(1, 20), prod[0], fecha.isoformat(), cant, desc])
pedidos.sort(key=lambda p: p[3])

if __name__ == "__main__":
    escribir("clientes.csv", ["id_cliente", "nombre", "ciudad", "segmento", "fecha_registro"], clientes)
    escribir("productos.csv", ["id_producto", "nombre", "categoria", "precio_unitario"],
             [list(p) for p in PRODUCTOS])
    escribir("pedidos.csv", ["id_pedido", "id_cliente", "id_producto", "fecha_pedido",
                             "cantidad", "descuento_pct"], pedidos)
