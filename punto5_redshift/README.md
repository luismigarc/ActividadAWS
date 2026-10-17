# Punto 5 – Amazon Redshift Serverless

## Elección: Serverless con 4 RPU de base (us-east-1)
- **Serverless** cobra por segundo solo mientras hay consultas (mínimo 60 s por cobro): 0,375 USD por RPU-hora en us-east-1. Con 4 RPU, 1 hora activa ≈ 1,50 USD; el taller usa unos minutos.
- **Provisionado** (ra3.large, un nodo) cobra cada hora que el clúster está encendido, haya o no consultas. Para un taller de pocas horas con uso intermitente sale más caro y además hay que acordarse de pausarlo.
- Los 4 RPU de base están disponibles en us-east-1 (soportan hasta 32 TB y 100 columnas por tabla, más que suficiente). Si la región no lo permite, el script usa 8 RPU automáticamente. Las cuentas nuevas pueden tener 300 USD de crédito de prueba de Redshift Serverless.

## Seguridad
- **Contraseña del administrador**: `create_namespace(manageAdminPassword=True)`. Redshift la genera, la guarda en Secrets Manager y la rota; nadie la escribe ni la lee.
- **Programa Python**: envía el SQL con la API de datos (`redshift-data`) usando `SecretArn` = ARN de ese secreto. El código nunca contiene ni imprime la contraseña.
- **Rol para COPY** (`taller-ingdata-p5-redshift-s3-role`): confianza en `redshift.amazonaws.com` (y `redshift-serverless.amazonaws.com`); permisos `s3:GetObject` en `redshift/datos/*` y `s3:ListBucket`/`s3:GetBucketLocation` en el bucket. Se asocia al namespace como rol por defecto.
- **Red**: workgroup en la VPC por defecto, `publiclyAccessible=False`. La API de datos y Query Editor v2 no necesitan acceso público.

### Conexión desde un cliente SQL local (opcional)
1. Workgroup → *Network and security* → **Publicly accessible = On** (o `update_workgroup(publiclyAccessible=True)`); requiere subredes con ruta a un Internet Gateway (la VPC por defecto las tiene).
2. Grupo de seguridad del workgroup: entrada **TCP 5439 desde su IP/32**.
3. Cliente (DBeaver, etc.): host = endpoint del workgroup, puerto 5439, base `tienda`, usuario `admin_taller`, contraseña sacada de Secrets Manager (o credenciales IAM temporales con `get_credentials`). SSL obligatorio.
4. Al terminar, vuelva a cerrar el acceso público.

## Datos (`datos/`)
- `clientes.csv` (20), `productos.csv` (10), `pedidos.csv` (120). `pedidos` referencia a clientes y productos (modelo estrella).
- `verificar_local.py` ejecuta las mismas consultas en SQLite para conocer el resultado esperado (`resultados_esperados/`). El script de Redshift compara automáticamente.

## Ejecución
```bash
uv run python punto5_redshift/redshift_serverless.py todo     # ~5-10 min (creación del workgroup)
# Opcional: Query Editor v2 -> conectar con "AWS Secrets Manager" y el secreto del admin
uv run python punto5_redshift/redshift_serverless.py limpiar
```

## SQL
- `sql/01_crear_tablas.sql`: DDL con `DISTSTYLE ALL` en las dimensiones y `DISTKEY(id_cliente) SORTKEY(fecha_pedido)` en los hechos.
- `sql/02_copy.sql`: `COPY ... FROM 's3://...' IAM_ROLE '<rol>' FORMAT AS CSV IGNOREHEADER 1`.
- `sql/03_consultas.sql`: q1 filtro, q2 unión, q3 agregación, q4 combinada (unión + agregación + HAVING).
