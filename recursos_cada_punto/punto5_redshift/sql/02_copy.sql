-- Plantilla de carga. El programa reemplaza {bucket}, {prefijo}, {rol} y {region}.
COPY clientes  FROM 's3://{bucket}/{prefijo}/clientes.csv'  IAM_ROLE '{rol}' FORMAT AS CSV IGNOREHEADER 1 DATEFORMAT 'YYYY-MM-DD' REGION '{region}';
COPY productos FROM 's3://{bucket}/{prefijo}/productos.csv' IAM_ROLE '{rol}' FORMAT AS CSV IGNOREHEADER 1 REGION '{region}';
COPY pedidos   FROM 's3://{bucket}/{prefijo}/pedidos.csv'   IAM_ROLE '{rol}' FORMAT AS CSV IGNOREHEADER 1 DATEFORMAT 'YYYY-MM-DD' REGION '{region}';
