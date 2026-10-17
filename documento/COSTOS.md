# Costos de la actividad AWS

**Universidad EIA — Ingeniería de Datos — Actividad AWS 2026-2**

> **Alcance:** estimaciones orientativas en USD, sin impuestos y sin aplicar créditos ni beneficios de capa gratuita, salvo donde se indique. Los precios dependen de la región, modalidad, fecha y configuración. **Amazon DocumentDB se desplegó en `us-east-1` (Norte de Virginia)**. No debe asumirse que todos los demás recursos se desplegaron en esa misma región. Validar las tarifas y la elegibilidad de cada cuenta en [AWS Pricing Calculator](https://calculator.aws/) y en las páginas oficiales de precios.

## Punto 1 — AWS Secrets Manager

Secrets Manager cobra por los secretos almacenados y las llamadas a su API:

| Concepto | Precio orientativo | Ejemplo |
|---|---:|---|
| Secreto almacenado | USD 0,40/secreto-mes | Una hora ≈ USD 0,00055, suponiendo 730 h/mes |
| Llamadas API | USD 0,05/10.000 llamadas | 2.592.000 llamadas ≈ USD 12,96 |
| Lectura con caché de 5 minutos | Misma tarifa API | 8.640 llamadas/mes ≈ USD 0,0432 |

Si una aplicación consulta un secreto cada segundo durante 30 días, genera aproximadamente 2,59 millones de llamadas y cerca de USD 13 de costo de API. En cambio, una caché en memoria con TTL de cinco minutos puede reducir las consultas a unas 8.640 por mes **por proceso de aplicación**, sin contar reinicios, errores o lecturas extraordinarias. La caché debe actualizarse cuando vence el TTL o cuando cambian las credenciales. Evitar guardar contraseñas en archivos, repositorios o registros.

La prueba gratuita y las condiciones de eliminación de secretos dependen de la oferta vigente y la elegibilidad de la cuenta.

## Punto 2 — Despliegue con Terraform, Boto3 y AWS CLI

Terraform, Boto3 y AWS CLI son **métodos de administración**, no tres modalidades distintas de precio para los mismos recursos. El costo depende de los recursos creados y de cuánto tiempo permanecen activos. Si se eliminan los recursos entre cada implementación, los costos corresponden a cada periodo de uso, no a tres despliegues simultáneos.

La siguiente tabla reproduce un **escenario de referencia** de EC2 `t3.micro`, disco EBS de 8 GB, RDS PostgreSQL `db.t4g.micro`, almacenamiento RDS de 20 GB y un secreto. **Verificar el motor y la clase de RDS realmente desplegados antes de usarla como costo efectivo.**

| Componente | Tarifa orientativa | 1 hora | 1 semana (168 h) |
|---|---:|---:|---:|
| EC2 `t3.micro` | USD 0,0104/h | 0,0104 | 1,7472 |
| EBS gp3, 8 GB | USD 0,08/GB-mes | 0,0009 | 0,1473 |
| RDS PostgreSQL `db.t4g.micro`, Single-AZ | USD 0,016/h | 0,0160 | 2,6880 |
| Almacenamiento RDS, 20 GB | USD 0,115/GB-mes | 0,0032 | 0,5293 |
| Un secreto en Secrets Manager | USD 0,40/mes | 0,0005 | 0,0921 |
| Bucket S3 vacío, sin operaciones | — | ≈ 0 | ≈ 0 |
| **Total aproximado, sin IPv4 pública** | | **0,0310** | **5,20** |

**Posibles adicionales:** una dirección IPv4 pública facturable suma aproximadamente USD 0,005/h (USD 0,84 por semana); también pueden cobrarse snapshots, solicitudes S3, transferencias y almacenamiento persistente. Detener una EC2 no elimina automáticamente los cargos de su volumen EBS. La capa gratuita no debe darse por supuesta: depende del tipo de cuenta y las condiciones actuales.

## Punto 3 — Amazon DocumentDB (`us-east-1`)

### Configuración utilizada

- **Región:** `us-east-1` (Norte de Virginia).
- **Modalidad:** DocumentDB Serverless.
- **Capacidad:** mínimo **0,5 DCU** y máximo **1 DCU**.
- **Conectividad:** instancia EC2 `t3.micro` en la misma VPC, túnel SSH y TLS.
- **Credenciales:** Secrets Manager.

### Comparación: Serverless frente a aprovisionado

Precios de referencia para el cálculo: **USD 0,0822/DCU-h** para Serverless y **USD 0,078/h** para una instancia aprovisionada `db.t3.medium` en `us-east-1`. Estas cifras deben verificarse contra la tarifa vigente y la configuración facturable del clúster.

| Modalidad | Cómputo por hora | 3 horas | 8 horas |
|---|---:|---:|---:|
| Serverless al mínimo de **0,5 DCU** | **USD 0,0411** | **USD 0,1233** | **USD 0,3288** |
| Serverless a **1 DCU** | USD 0,0822 | USD 0,2466 | USD 0,6576 |
| Aprovisionado `db.t3.medium` | USD 0,0780 | USD 0,2340 | USD 0,6240 |

**Interpretación:** para una práctica corta, **Serverless resulta más económico en cómputo si permanece cerca del mínimo de 0,5 DCU**. Si consume 1 DCU de manera sostenida, el cómputo sería ligeramente más caro que el de `db.t3.medium`. El servicio no escala automáticamente a cero con esta configuración; sigue existiendo un mínimo facturable mientras está activo. Una promoción o prueba gratuita aplicable a `db.t3.medium` puede cambiar la conclusión para una cuenta elegible.

Estos cálculos comparan **cómputo**, no el costo integral del clúster: almacenamiento, operaciones de E/S, backups y otros conceptos deben añadirse según su consumo real. Como referencias de la práctica: almacenamiento estándar ≈ **USD 0,10/GB-mes** y E/S ≈ **USD 0,20 por millón de solicitudes**; confirmar las tarifas vigentes y la modalidad de almacenamiento.

### ¿Cuánto agrega la EC2 del túnel?

| Componente | Costo aproximado por hora |
|---|---:|
| EC2 Linux `t3.micro` | USD 0,0104 |
| IPv4 pública | USD 0,0050 |
| EBS gp3 de 8 GB | USD 0,0009 |
| **Total del túnel** | **USD 0,0163/h** |

Para **3 horas**, el túnel suma aproximadamente **USD 0,0489**; para **8 horas**, **USD 0,1304**. En comparación con Serverless a 0,5 DCU, supone cerca del **40 % adicional sobre el costo de cómputo de DocumentDB**. No se incluyen transferencia de datos, solicitudes adicionales ni posibles beneficios de capa gratuita. Si el secreto de Secrets Manager se factura por separado, debe agregarse su costo proporcional.

**Conclusión del punto 3:** la elección de DocumentDB Serverless con mínimo de 0,5 DCU fue razonable para las pruebas de corta duración en `us-east-1`. La EC2 del túnel tiene un costo pequeño en términos absolutos, pero significativo frente al costo de cómputo mínimo de DocumentDB. Se deben eliminar el clúster, la instancia, la EC2 y los recursos auxiliares facturables al terminar.

## Punto 4 — Amazon Neptune

Neptune aprovisionado cobra por instancia-hora; Neptune Serverless cobra por capacidad consumida en NCU-hora. Para este escenario se consideran **USD 0,1608/NCU-h** y un mínimo de **1 NCU**, por lo que el costo mínimo orientativo de cómputo sería USD 0,1608/h. Una instancia aprovisionada pequeña podría costar menos por hora, pero **la clase y su precio deben verificarse en la región elegida** antes de declarar una ganadora.

Otros conceptos posibles: almacenamiento ≈ USD 0,10/GB-mes, solicitudes de E/S ≈ USD 0,20/millón y backups o snapshots según retención y modalidad. Neptune admite opciones de acceso mediante endpoints públicos cuando se habilitan y cumplen las condiciones de red y seguridad; **no debe afirmarse que una EC2 sea siempre obligatoria**. Una IPv4 pública de EC2, si se utiliza, puede agregar USD 0,005/h.

Aunque no se ejecuten consultas, pueden seguir cobrando la instancia aprovisionada o la capacidad mínima Serverless, el almacenamiento y otros recursos persistentes. La elegibilidad para pruebas gratuitas depende de la cuenta.

## Punto 5 — Amazon Redshift

En Redshift Serverless se cobra la capacidad de procesamiento en **RPU-hora**, con mínimo de facturación aplicable a cada periodo de actividad; el almacenamiento se factura por separado. En aprovisionado se cobra por los nodos mientras el clúster está activo, salvo las condiciones de pausa que correspondan.

| Concepto | Precio orientativo | Ejemplo |
|---|---:|---|
| Serverless | USD 0,375/RPU-h | 4 RPU × 1 h = **USD 1,50** |
| Almacenamiento administrado | USD 0,024/GB-mes | 1 GB por un mes ≈ USD 0,024 |
| Aprovisionado | Depende de clase y nodos | Verificar precio regional antes de comparar |

**Conclusión:** para consultas cortas y esporádicas, Serverless puede ser conveniente porque evita mantener nodos aprovisionados durante periodos de inactividad. **No es necesariamente más barato para cargas continuas.** Al finalizar deben revisarse el almacenamiento, las instantáneas, los secretos y los recursos S3 que permanezcan.

## Punto 6 — AWS Glue Data Catalog, Crawlers y Athena

| Servicio | Tarifa orientativa | Ejemplo |
|---|---:|---|
| Glue Crawler | USD 0,44/DPU-h | 1 DPU × 10 min ≈ USD 0,0733 por ejecución |
| Dos ejecuciones mínimas de crawler | — | ≈ **USD 0,1467** |
| Glue Data Catalog | Primer millón de objetos y solicitudes al mes según condiciones de la oferta | ≈ USD 0 para un catálogo pequeño elegible |
| S3 Standard | USD 0,023/GB-mes | Archivos CSV pequeños: costo muy bajo |
| Athena SQL | USD 5/TB escaneado | 10 MB facturables ≈ **USD 0,00005** |

En Athena, para las consultas SQL bajo la modalidad de pago por datos escaneados, puede aplicar un mínimo de **10 MB por consulta**. Las consultas DDL y las consultas fallidas no generan cargos por datos escaneados, aunque otros servicios relacionados pueden facturar sus propios recursos.

**Cómo reducir costos:** almacenar los datos en formatos columnares (Parquet u ORC), comprimir, particionar por campos de filtro frecuentes y evitar leer columnas innecesarias. La partición `mes=2026-10`, por ejemplo, permite que Athena descarte otras particiones cuando la consulta filtra correctamente por `mes`.

## Consideraciones generales

1. **La región importa:** en este documento **DocumentDB corresponde a `us-east-1`**; los precios de otros puntos son escenarios orientativos y deben cotejarse con su región real.
2. **Horas de uso:** las tablas de 3 u 8 horas son ejemplos, no una medición automática de la duración efectiva del laboratorio.
3. **Pruebas gratuitas:** solo aplican cuando la cuenta y el recurso cumplen las condiciones vigentes; no deben restarse sin comprobar la elegibilidad.
4. **Eliminar recursos:** además de instancias y clústeres, revisar discos, IPv4 públicas, secretos, snapshots, buckets y otros recursos persistentes.
5. **Evidencias y facturación:** las estimaciones no sustituyen el gasto observado en AWS Billing/Cost Explorer.

## Fuentes oficiales para actualizar precios

- [AWS Pricing Calculator](https://calculator.aws/)
- [AWS Secrets Manager Pricing](https://aws.amazon.com/secrets-manager/pricing/)
- [Amazon EC2 Pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
- [Amazon RDS Pricing](https://aws.amazon.com/rds/pricing/)
- [Amazon DocumentDB Pricing](https://aws.amazon.com/documentdb/pricing/)
- [Amazon Neptune Pricing](https://aws.amazon.com/neptune/pricing/)
- [Amazon Redshift Pricing](https://aws.amazon.com/redshift/pricing/)
- [AWS Glue Pricing](https://aws.amazon.com/glue/pricing/)
- [Amazon Athena Pricing](https://aws.amazon.com/athena/pricing/)
