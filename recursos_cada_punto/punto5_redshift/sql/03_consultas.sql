-- name: q1_filtro
-- pregunta: ¿Qué pedidos del tercer trimestre de 2026 (jul-sep) fueron de 3 o más unidades?
SELECT id_pedido, fecha_pedido, id_cliente, id_producto, cantidad, descuento_pct
FROM pedidos
WHERE fecha_pedido BETWEEN '2026-07-01' AND '2026-09-30'
  AND cantidad >= 3
ORDER BY fecha_pedido, id_pedido;

-- name: q2_union
-- pregunta: ¿Cuáles son los 10 pedidos de mayor valor neto hechos por clientes de Medellín, con el nombre del cliente y del producto?
SELECT p.id_pedido, p.fecha_pedido, c.nombre AS cliente, pr.nombre AS producto,
       p.cantidad, p.descuento_pct,
       ROUND(p.cantidad * pr.precio_unitario * (1 - p.descuento_pct / 100.0), 0) AS valor_neto
FROM pedidos p
JOIN clientes  c  ON c.id_cliente  = p.id_cliente
JOIN productos pr ON pr.id_producto = p.id_producto
WHERE c.ciudad = 'Medellin'
ORDER BY valor_neto DESC, p.id_pedido
LIMIT 10;

-- name: q3_agregacion
-- pregunta: ¿Cuánto se vendió (neto) por categoría de producto y segmento de cliente, y cuál fue el ticket promedio?
SELECT pr.categoria, c.segmento,
       COUNT(*)        AS num_pedidos,
       SUM(p.cantidad) AS unidades,
       ROUND(SUM(p.cantidad * pr.precio_unitario * (1 - p.descuento_pct / 100.0)), 0) AS ventas_netas,
       ROUND(AVG(p.cantidad * pr.precio_unitario * (1 - p.descuento_pct / 100.0)), 0) AS ticket_promedio
FROM pedidos p
JOIN productos pr ON pr.id_producto = p.id_producto
JOIN clientes  c  ON c.id_cliente  = p.id_cliente
GROUP BY pr.categoria, c.segmento
ORDER BY ventas_netas DESC;

-- name: q4_top_clientes
-- pregunta: ¿Qué 5 clientes generaron más ventas netas y cuántos pedidos hicieron? (filtro + unión + agregación + HAVING)
SELECT c.id_cliente, c.nombre, c.ciudad, c.segmento,
       COUNT(*) AS num_pedidos,
       ROUND(SUM(p.cantidad * pr.precio_unitario * (1 - p.descuento_pct / 100.0)), 0) AS ventas_netas
FROM pedidos p
JOIN clientes  c  ON c.id_cliente  = p.id_cliente
JOIN productos pr ON pr.id_producto = p.id_producto
GROUP BY c.id_cliente, c.nombre, c.ciudad, c.segmento
HAVING COUNT(*) >= 5
ORDER BY ventas_netas DESC
LIMIT 5;
