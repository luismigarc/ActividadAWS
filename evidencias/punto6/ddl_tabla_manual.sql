CREATE EXTERNAL TABLE IF NOT EXISTS ventas_manual (
  id_venta bigint,
  fecha date,
  ciudad string,
  codigo_postal string,
  producto string,
  categoria string,
  cantidad int,
  precio_unitario decimal(12,2),
  cliente_vip boolean
)
PARTITIONED BY (mes string)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://taller-ingdata-p6-129898048658-us-east-1/ventas/'
TBLPROPERTIES ('skip.header.line.count'='1', 'classification'='csv');
