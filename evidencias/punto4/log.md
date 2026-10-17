# Evidencias punto4


## Paso 1 - Red, seguridad y clúster Neptune con endpoint público  
_2026-10-15 20:53:11_

- Evidencia: `01_identidad_usada.json` (2026-10-15 20:53:29)

## Paso 1 - Red, seguridad y clúster Neptune con endpoint público  
_2026-10-15 20:55:34_

- Evidencia: `02_identidad_usada.json` (2026-10-15 20:55:51)

## Paso 1 - Red, seguridad y clúster Neptune con endpoint público  
_2026-10-15 20:58:38_

- Evidencia: `03_identidad_usada.json` (2026-10-15 20:58:55)

## Paso 1 - Red, seguridad y clúster Neptune con endpoint público  
_2026-10-15 21:01:02_

- Evidencia: `04_identidad_usada.json` (2026-10-15 21:01:18)
- Versión del motor: 1.4.8.1 (públicos desde 1.4.6) | clase: db.t4g.medium
- Evidencia: `05_versiones_y_clases.json` (2026-10-15 21:01:53)
- Evidencia: `06_vpc_rutas.json` (2026-10-15 21:02:10)
- VPC por defecto vpc-07bf2d2d4397b6f43: ruta 0.0.0.0/0 -> ['igw-0e479c981895c5f90'] (subredes públicas)
- Evidencia: `07_subnet_group.json` (2026-10-15 21:02:11)
- Evidencia: `08_security_group.json` (2026-10-15 21:02:12)
- Grupo de seguridad sg-06b963e2ace085e8c: TCP 8182 solo desde 190.240.81.246/32
- Evidencia: `09_cluster.json` (2026-10-15 21:12:54)
- Evidencia: `10_instancia.json` (2026-10-15 21:12:54)
- Endpoint del clúster: taller-ingdata-neptune.cluster-cyjau6o6m52z.us-east-1.neptune.amazonaws.com:8182 | IAM auth=True | PubliclyAccessible=True

## Prueba de conexión desde el computador local (HTTPS + SigV4)  
_2026-10-15 21:12:54_

- Evidencia: `11_engine_status.json` (2026-10-15 21:13:11)
- Estado: healthy | versión 1.4.8.1.R1 | IAMAuthentication: enabled

## Paso 2 - Carga del grafo (openCypher)  
_2026-10-15 21:13:11_

- 6 vértices :Estudiante
- 2 vértices :Profesor
- 4 vértices :Curso
- 2 vértices :Ciudad
- 7 aristas :CONOCE
- 11 aristas :INSCRITO_EN
- 4 aristas :DICTA
- 3 aristas :REQUIERE
- 8 aristas :VIVE_EN

**conteo_vertices** 

| etiqueta | total |
|---|---|
| Ciudad | 2 |
| Curso | 4 |
| Estudiante | 6 |
| Profesor | 2 |


**conteo_aristas** 

| tipo | total |
|---|---|
| CONOCE | 7 |
| DICTA | 4 |
| INSCRITO_EN | 11 |
| REQUIERE | 3 |
| VIVE_EN | 8 |

- Total: 14 vértices y 33 relaciones
- Archivo: `modelo_grafo.md`

## Paso 3 - Consultas que recorren relaciones (Python + openCypher y Gremlin)  
_2026-10-15 21:16:34_

- **q1_recomendar_amigos** - ¿A quién podría conocer Ana? Amigos de sus amigos que aún no conoce (2 saltos por CONOCE).
- Evidencia: `12_cypher_q1_recomendar_amigos.json` (2026-10-15 21:16:52)

**q1_recomendar_amigos** - ¿A quién podría conocer Ana? Amigos de sus amigos que aún no conoce (2 saltos por CONOCE). (17639 ms)

| sugerido | amigos_en_comun | num_amigos_comun |
|---|---|---|
| Diego | Carla -> Bruno | 2 |
| Elena | Carla | 1 |

- **q2_profesores_de_medellin** - ¿Qué profesores dictan cursos a estudiantes que viven en Medellín, en qué cursos y a quiénes? (3 saltos: Ciudad<-VIVE_EN-Estudiante-INSCRITO_EN->Curso<-DICTA-Profesor)
- Evidencia: `13_cypher_q2_profesores_de_medellin.json` (2026-10-15 21:17:09)

**q2_profesores_de_medellin** - ¿Qué profesores dictan cursos a estudiantes que viven en Medellín, en qué cursos y a quiénes? (3 saltos: Ciudad<-VIVE_EN-Estudiante-INSCRITO_EN->Curso<-DICTA-Profesor) (17319 ms)

| profesor | curso | estudiantes | nota_promedio |
|---|---|---|---|
| Prof. Gómez | Bases de Datos | Carla | 4.7 |
| Prof. Gómez | Ingeniería de Datos | Diego -> Ana | 4.0 |
| Prof. Rojas | Computación en la Nube | Carla -> Ana | 4.05 |
| Prof. Rojas | Visión Artificial | Diego | 4.4 |

- **q3_ruta_prerrequisitos** - ¿Qué cursos hay que aprobar antes de Visión Artificial? (camino de longitud variable por REQUIERE)
- Evidencia: `14_cypher_q3_ruta_prerrequisitos.json` (2026-10-15 21:17:26)

**q3_ruta_prerrequisitos** - ¿Qué cursos hay que aprobar antes de Visión Artificial? (camino de longitud variable por REQUIERE) (17312 ms)

| prerrequisito | nivel |
|---|---|
| Ingeniería de Datos | 1 |
| Bases de Datos | 2 |

- **q4_cadena_contactos** - ¿Por qué cadena de conocidos llega Ana hasta Felipe? (caminos de hasta 4 saltos por CONOCE)
- Evidencia: `15_cypher_q4_cadena_contactos.json` (2026-10-15 21:17:44)

**q4_cadena_contactos** - ¿Por qué cadena de conocidos llega Ana hasta Felipe? (caminos de hasta 4 saltos por CONOCE) (17125 ms)

| nodos | saltos |
|---|---|
| Ana -> Carla -> Diego -> Felipe | 3 |
| Ana -> Bruno -> Diego -> Felipe | 3 |
| Ana -> Carla -> Elena -> Felipe | 3 |

- Evidencia: `16_gremlin_g1_recomendar_amigos.json` (2026-10-15 21:18:02)

**g1_recomendar_amigos** - Igual que q1 en Gremlin: amigos de amigos de Ana que no son sus amigos.

| resultado |
|---|
| "Diego" |
| "Elena" |

- Evidencia: `17_gremlin_g2_profesores_de_medellin.json` (2026-10-15 21:18:02)

**g2_profesores_de_medellin** - Igual que q2 en Gremlin: profesores de los estudiantes que viven en Medellín.

| resultado |
|---|
| "Prof. Gómez" |
| "Prof. Rojas" |

- Evidencia: `18_gremlin_g3_ruta_prerrequisitos.json` (2026-10-15 21:18:02)

**g3_ruta_prerrequisitos** - Igual que q3 en Gremlin: caminos de prerrequisitos desde Visión Artificial.

| resultado |
|---|
| {"labels": [[], []], "objects": ["Visión Artificial", "Ingeniería de Datos"]} |
| {"labels": [[], [], []], "objects": ["Visión Artificial", "Ingeniería de Datos", "Bases de Datos"]} |


## Paso 4 - Costos  
_2026-10-15 21:18:02_

- Evidencia: `19_precios_api.json` (2026-10-15 21:18:53)

**estimacion_costos** 

| componente | uso | costo_usd |
|---|---|---|
| Instancia db.t4g.medium (aprovisionada) | 0.098 USD/h (ref.) | 1 h: $0.098 | semana: $16.46 | uso real ~0.28 h: $0.027 |
| Serverless mínimo 1 NCU (comparación) | 0.1608 USD/NCU-h | 1 h: $0.161 | semana: $27.01 |
| Almacenamiento | 0.0000 GB usados (VolumeBytesUsed) | $0.0000/mes |
| I/O | pocas miles de peticiones | 0.2 USD/millón -> ~$0.00 |
| Endpoint público | sin EC2 ni túnel | $0.00 adicional (solo transferencia de datos) |
| Capa gratuita (cuentas nuevas) | 750 h t3/t4g.medium por 30 días | posible $0 |


## Limpieza - eliminación y verificación  
_2026-10-15 21:42:18_

- Solicitada eliminación de la instancia
- Solicitada eliminación del clúster (sin snapshot final)

**verificacion_eliminacion** 

| recurso | estado |
|---|---|
| Instancia | no existe (DBInstanceNotFound) |
| Clúster | no existe (DBClusterNotFoundFault) |
| Snapshots del clúster | ninguno |
| DB subnet group | no existe (DBSubnetGroupNotFoundFault) |
| Security group | no existe (InvalidGroup.NotFound) |

