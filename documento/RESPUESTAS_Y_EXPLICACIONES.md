# Respuestas teóricas y explicaciones

## Punto 1 — AWS Secrets Manager

### ¿Qué es?
Servicio administrado para **guardar, recuperar, auditar y rotar secretos**. Cada secreto se cifra en
reposo con AWS KMS (por defecto con la clave administrada `aws/secretsmanager`), tiene **versiones** con
etiquetas (`AWSCURRENT`, `AWSPREVIOUS`, `AWSPENDING`) y cada acceso queda registrado en CloudTrail. Se
integra de forma nativa con RDS, Aurora, Redshift y DocumentDB, que pueden **administrar ellos mismos**
la contraseña maestra dentro de Secrets Manager.



### ¿Qué información permite guardar?
Cualquier texto o binario de hasta **64 KB**, normalmente en JSON clave-valor: credenciales de bases de
datos (usuario, contraseña, host, puerto), claves de API, tokens OAuth, llaves SSH o privadas, cadenas
de conexión y certificados. No es para datos de negocio ni configuración no sensible (para eso está
Parameter Store).



### ¿Cómo se controla quién lo lee?
1. **Políticas de identidad IAM** (usuario o rol): `secretsmanager:GetSecretValue` sobre el ARN exacto del secreto (mínimo privilegio, como en el punto 1).
2. **Política basada en recursos** del propio secreto: permite o niega a principales concretos, incluso de otras cuentas.
3. **Política de la clave KMS**: para descifrar hace falta `kms:Decrypt` (implícito con la clave administrada por AWS; explícito con una clave propia).
4. **Condiciones**: etiquetas (ABAC), `aws:SourceVpce` (solo desde un VPC endpoint), `aws:SourceIp`, MFA.
5. **Auditoría**: CloudTrail registra quién leyó qué secreto y cuándo.



### Crear, recuperar y rotar
| Operación | Qué hace | API |
|---|---|---|
| **Crear** | Registra el secreto y su primera versión (`AWSCURRENT`), cifrada con KMS | `CreateSecret` |
| **Recuperar** | La aplicación, autenticada con IAM, pide el valor en tiempo de ejecución; por defecto recibe `AWSCURRENT` | `GetSecretValue` |
| **Actualizar** | Guarda un valor nuevo y mueve `AWSCURRENT` a esa versión (la anterior pasa a `AWSPREVIOUS`). **No cambia** la contraseña en la base de datos | `PutSecretValue` / `UpdateSecret` |
| **Rotar** | Cambia la credencial **en el sistema destino y en el secreto** de forma coordinada: una función Lambda ejecuta `createSecret → setSecret → testSecret → finishSecret` (o rotación administrada en RDS/Redshift/DocumentDB), con un calendario (p. ej., cada 30 días) | `RotateSecret` |

El punto 1 demuestra que, como el programa siempre pide `AWSCURRENT`, recibe el valor nuevo **sin cambiar el código**.




## Punto 2 — Terraform, SDK y AWS CLI

### ¿Qué es Terraform?
Herramienta de **infraestructura como código declarativa** (HCL). Se describe el estado deseado y
Terraform calcula y aplica las diferencias:
- **Proveedores** (`hashicorp/aws`) traducen los recursos a llamadas a la API de AWS.
- **Recursos** (`aws_instance`, `aws_db_instance`…) y **data sources** (VPC por defecto, AMI).
- **Estado** (`terraform.tfstate`): relación entre el código y los recursos reales.
- Flujo: `terraform init` (descarga proveedores) → `validate` → `plan` (muestra qué va a crear, cambiar o destruir) → `apply` (lo ejecuta en el orden del grafo de dependencias) → `destroy` (elimina en orden inverso).



### Autenticación de `user_cli`
Una clave de acceso (Access Key ID + Secret) del usuario IAM se guarda en el perfil `user_cli` de
`~/.aws/credentials` (WSL). AWS CLI, Boto3 y el proveedor de Terraform usan la **misma cadena de
credenciales** (variables de entorno → perfil compartido → SSO → metadatos de instancia) y firman cada
petición con **SigV4**. La autorización la dan las políticas IAM del usuario. Las claves no se guardan en
Secrets Manager porque, para leer un secreto, la herramienta ya tiene que estar autenticada en AWS.



### Estado de Terraform
Guarda **en texto plano** todos los atributos de cada recurso: IDs, ARN, IP, endpoints, configuración y
cualquier valor sensible que reciba (si se escribiera `password = "..."` en `aws_db_instance`, quedaría
en el estado). Con `manage_master_user_password = true` solo se guarda el ARN del secreto. El script
`ejecutar_terraform.py` revisa automáticamente que no haya contraseñas en el estado. El estado no se sube
al repositorio; en equipos se usa un backend remoto cifrado (S3 con bloqueo).



### Comparación de métodos
| | Terraform | Boto3 | AWS CLI |
|---|---|---|---|
| Paradigma | Declarativo | Imperativo (Python) | Imperativo (comandos) |
| Sabe qué creó | Sí (estado) | Solo si lo programo | Solo si lo guardo |
| Vista previa | `plan` | No | No |
| Orden y dependencias | Automáticos | Waiters manuales | `aws ... wait` manuales |
| Repetir sin duplicar | Sí (idempotente) | No, salvo que lo programe | No |
| Borrado | `destroy` | Código en orden inverso | Comandos en orden inverso |
| Uso ideal | Infraestructura reproducible y versionada | Automatización con lógica propia | Tareas puntuales y scripts cortos |

Los tiempos reales quedan en `evidencias/punto2/tiempos.csv`. El tiempo lo domina RDS (5–10 min), igual en los tres métodos.




## Punto 3 — Amazon DocumentDB

### DocumentDB frente a MongoDB: diferencias que afectan una aplicación existente
1. **No es MongoDB**: es un motor propio de AWS que implementa la API y el protocolo de MongoDB (compatibilidad 3.6, 4.0 y 5.0). Algunos operadores, etapas de agregación y comandos no están soportados o se comportan distinto (p. ej., `mapReduce`, `$where`, funciones JavaScript, algunas opciones de `$lookup`, colaciones). Hay que revisar la aplicación con la herramienta de compatibilidad.
2. **Retryable writes no soportadas**: los drivers modernos las activan por defecto, así que hay que usar `retryWrites=false` o fallarán las escrituras.
3. **Red y seguridad**: solo es accesible dentro de una VPC (sin endpoint público), con TLS activado por defecto y el certificado de AWS (`global-bundle.pem`). Desde fuera hace falta un túnel, una VPN, etc.
4. **Arquitectura y escalado**: el almacenamiento es compartido y se replica 6 veces en 3 zonas de disponibilidad; las réplicas de lectura (hasta 15) leen del mismo volumen. No hay *sharding* en clústeres basados en instancias (sí en Elastic Clusters). La consistencia de lectura en réplicas es eventual.
5. **Otros**: change streams deben habilitarse por colección; los límites de transacciones son distintos; no existen funciones exclusivas de Atlas (Atlas Search, Triggers, etc.); la autenticación usa SCRAM-SHA-1.



## Punto 4 — Amazon Neptune

### Neptune frente a Neo4j
| | Amazon Neptune | Neo4j |
|---|---|---|
| Modelos de datos | **Grafo de propiedades** (LPG) **y RDF** (W3C) en el mismo servicio | Grafo de propiedades etiquetado (RDF solo con el plugin *neosemantics*) |
| Lenguajes | **Gremlin** (Apache TinkerPop), **openCypher** y **SPARQL 1.1** | **Cypher** completo (+ procedimientos APOC); GQL |
| Herramientas | Graph Notebook / Neptune Workbench (Jupyter), Graph Explorer, API `neptunedata`, cargador masivo desde S3, Neptune Streams, CloudWatch, Neptune Analytics para algoritmos | Neo4j Browser, Bloom, Desktop, cypher-shell, `neo4j-admin import`, Graph Data Science (algoritmos), AuraDB (administrado) |
| Operación | Totalmente administrado en AWS: VPC, IAM, almacenamiento autoescalable hasta 128 TiB, hasta 15 réplicas | Autogestionado (Community/Enterprise) o AuraDB en la nube |
| Autenticación | IAM (SigV4) opcional, obligatoria con endpoint público | Usuario y contraseña, roles |

En este taller se usó openCypher (muy parecido al Cypher de Neo4j) y las mismas consultas en Gremlin.



### Acceso desde local
- **Endpoint público** (elegido; Neptune ≥ 1.4.6, septiembre de 2025): la instancia se crea con `PubliclyAccessible=true` en subredes públicas (ruta `0.0.0.0/0` → Internet Gateway); el grupo de seguridad abre solo TCP 8182 a la IP del estudiante (/32), y la **autenticación IAM es obligatoria** (SigV4, la hace `boto3.client("neptunedata")`). No requiere EC2.
- **Túnel SSH con EC2**: bastión en subred pública + `ssh -L 8182:<endpoint>:8182`. Funciona con cualquier versión, pero añade una EC2 (≈ 0,016 USD/h con IPv4) y la gestión de llaves y del puerto 22. Con IAM auth, la firma SigV4 debe incluir el host real, no `localhost`.
- **¿Es necesario el proceso con EC2?** Ya no, si la versión es 1.4.6 o superior. **Otras maneras**: SSM Session Manager con *port forwarding* (sin abrir el puerto 22, pero sigue necesitando una instancia administrada), Neptune Workbench / Graph Notebook dentro de la VPC, AWS Client VPN o Site-to-Site VPN, y una Lambda o API Gateway dentro de la VPC que exponga las consultas.




## Punto 5 — Amazon Redshift

### ¿Qué es y para qué sirve?
Almacén de datos (*data warehouse*) **columnar y MPP** (procesamiento masivamente paralelo) para
**análisis OLAP**: consultas que recorren millones o miles de millones de filas con agregaciones, uniones
entre tablas de hechos y dimensiones, reportes de BI, tableros e históricos de varios años, consultas
sobre el data lake en S3 (Redshift Spectrum) y ML con SQL.



### Componentes principales
- **Provisionado**: *clúster* con **nodo líder** (recibe el SQL, planifica y combina resultados) y **nodos de cómputo** divididos en *slices* que procesan en paralelo; con nodos RA3 los datos viven en **Redshift Managed Storage** (RMS, en S3) con caché local.
- **Serverless**: **namespace** (bases de datos, esquemas, tablas, usuarios, almacenamiento y el secreto del administrador) + **workgroup** (cómputo en RPU, red, subredes, grupos de seguridad y endpoint).
- **Diseño físico**: almacenamiento columnar comprimido, **estilos de distribución** (`AUTO`, `EVEN`, `KEY`, `ALL`) y **llaves de ordenamiento** (*sort keys*) para leer menos bloques.
- **Carga y acceso**: `COPY` desde S3 en paralelo (con un rol IAM), `UNLOAD`, API de datos, Query Editor v2, drivers JDBC/ODBC, snapshots y *concurrency scaling*.



### Redshift frente a RDS
| | Amazon RDS | Amazon Redshift |
|---|---|---|
| Carga de trabajo | **OLTP**: muchas transacciones pequeñas (insertar o actualizar un pedido, consultar por ID) | **OLAP**: pocas consultas grandes que agregan millones de filas |
| Almacenamiento | Por filas | Por columnas, comprimido, MPP |
| Integridad | PK, FK y UNIQUE se hacen cumplir | PK y FK son informativas (no se validan) |
| Escala | Vertical + réplicas de lectura | Horizontal (nodos/RPU), petabytes |

**Casos**: **RDS** para la base transaccional de la tienda en línea (registrar pedidos, pagos e inventario en tiempo real). **Redshift** para analizar 3 años de ventas uniendo pedidos, clientes y marketing (ventas por región, mes y segmento).



### Interpretación de las consultas (resultados esperados, verificados en SQLite)
- **q1 – Filtro**: *¿Qué pedidos del tercer trimestre (julio–septiembre de 2026) fueron de 3 o más unidades?* → 19 de los 61 pedidos del trimestre (≈ 31 %) son compras de volumen. Se reparten entre julio (7), agosto (6) y septiembre (6). 8 de ellos se dieron sin descuento, es decir, el volumen no depende del descuento.
- **q2 – Unión (3 tablas)**: *¿Cuáles son los 10 pedidos de mayor valor neto de clientes de Medellín?* → Los encabezan el **Portátil 14** (dos pedidos de 3 unidades con 15 % de descuento, 8.922.450 c/u) y el **Escritorio en L**. **Pablo Vargas** aparece 4 veces y **Diego Restrepo** 3 veces en el top 10: unos pocos clientes corporativos concentran los pedidos grandes de la ciudad.
- **q3 – Agregación**: *¿Cuánto se vendió (neto) por categoría y segmento?* → Ventas netas totales ≈ 226,3 millones. **Tecnología–Corporativo** lidera con 90,8 M (40 % del total, 39 pedidos), seguido de Tecnología–Estándar (50,2 M) y Muebles–Corporativo (38,4 M). **Hogar** es la categoría más pequeña en todos los segmentos. El segmento **Premium** compra poca tecnología (7,0 M), una posible oportunidad comercial. El ticket promedio más alto es Tecnología–Estándar (≈ 3,14 M).
- **q4 – Combinada (unión + agregación + HAVING)**: *¿Qué 5 clientes con al menos 5 pedidos generaron más ventas?* → Pablo Vargas (Medellín, Corporativo, 26,4 M en 7 pedidos), Diego Restrepo (Medellín, Corporativo, 22,7 M en 10), Olga Gómez (Envigado, 22,0 M), Julián Mejía (Bogotá, 19,6 M) y Nicolás Gómez (Barranquilla, 18,5 M). El top 5 suma ≈ 109 M, cerca del 48 % de las ventas: alta concentración en pocos clientes.

El script compara automáticamente los resultados de Redshift con estos (columna "¿Coincide…?" del log).




## Punto 6 — AWS Glue Data Catalog

### ¿Qué almacena?
**Metadatos**, no datos: bases de datos, tablas (columnas y tipos, ubicación en S3, formato y SerDe,
clasificación, claves de partición, estadísticas), particiones, conexiones, definiciones de crawlers y
clasificadores. Es un *metastore* compatible con Hive que usan Athena, EMR, Glue ETL, Redshift
Spectrum y Lake Formation.



### Archivos en S3 frente a metadatos
- **S3** guarda los **archivos reales** (los CSV con los 35 registros).
- **El catálogo** guarda la **descripción** de esos archivos: dónde están, cómo leerlos y qué columnas tienen. Athena consulta S3 usando esa descripción (*schema-on-read*). Borrar una tabla externa del catálogo **no borra** los archivos de S3, y agregar archivos a la carpeta de una tabla no particionada los hace visibles sin tocar el catálogo. Una partición nueva, en cambio, debe registrarse (crawler, `MSCK REPAIR` o `ALTER TABLE ADD PARTITION`).



### Bases de datos, tablas y crawlers
- **Base de datos**: espacio de nombres lógico que agrupa tablas (`taller_ventas_db`).
- **Tabla**: definición de metadatos que apunta a una ubicación de S3 (`ventas`, con partición `mes`).
- **Crawler**: proceso que recorre un origen (S3, JDBC…), usa **clasificadores** para detectar el formato y el esquema, y **crea o actualiza** tablas y particiones del catálogo. Se puede programar y tiene políticas de cambio de esquema (actualizar, solo registrar en el log o eliminar).



### Credenciales
S3, Glue y Athena se autorizan **solo con IAM**: el usuario usa sus credenciales de AWS CLI y el crawler
asume un **rol** (`AWSGlueServiceRole` + lectura del prefijo), por lo que recibe credenciales temporales de
STS. No hay usuario ni contraseña de aplicación, así que **no hace falta un secreto**. Solo se usaría
Secrets Manager si el crawler leyera una base de datos mediante una *Glue Connection* JDBC.



### Crawler frente a tabla manual
| | Crawler | DDL manual |
|---|---|---|
| Esquema | Inferido; puede equivocarse (códigos postales como `bigint`, fechas como `string`) | Exacto, definido por usted |
| Particiones nuevas | Las registra al volver a ejecutarse | `MSCK REPAIR TABLE`, `ALTER TABLE ADD PARTITION` o *partition projection* |
| Cambios de esquema | Los detecta (o los registra en el log con `LOG`) | Manuales |
| Costo | DPU-hora (mínimo 10 min) | Gratis (DDL de Athena) |
| Cuándo usarlo | Datos nuevos o desconocidos, muchas carpetas o formatos | Esquemas conocidos y estables |
