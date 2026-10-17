-- Punto 5: modelo en estrella sencillo (2 dimensiones + 1 tabla de hechos)
-- Las tablas pequeñas se replican en todos los nodos (DISTSTYLE ALL) y la tabla
-- de hechos se distribuye por id_cliente y se ordena por fecha.
DROP TABLE IF EXISTS pedidos;
DROP TABLE IF EXISTS clientes;
DROP TABLE IF EXISTS productos;

CREATE TABLE clientes (
    id_cliente      INTEGER      NOT NULL PRIMARY KEY,
    nombre          VARCHAR(60)  NOT NULL,
    ciudad          VARCHAR(30)  NOT NULL,
    segmento        VARCHAR(20)  NOT NULL,
    fecha_registro  DATE         NOT NULL
) DISTSTYLE ALL;

CREATE TABLE productos (
    id_producto     INTEGER       NOT NULL PRIMARY KEY,
    nombre          VARCHAR(60)   NOT NULL,
    categoria       VARCHAR(30)   NOT NULL,
    precio_unitario DECIMAL(12,2) NOT NULL
) DISTSTYLE ALL;

CREATE TABLE pedidos (
    id_pedido       INTEGER  NOT NULL PRIMARY KEY,
    id_cliente      INTEGER  NOT NULL REFERENCES clientes(id_cliente),
    id_producto     INTEGER  NOT NULL REFERENCES productos(id_producto),
    fecha_pedido    DATE     NOT NULL,
    cantidad        SMALLINT NOT NULL,
    descuento_pct   SMALLINT NOT NULL
) DISTKEY(id_cliente) SORTKEY(fecha_pedido);
