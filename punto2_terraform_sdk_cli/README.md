# Punto 2 – Terraform, Boto3 y AWS CLI con `user_cli`

Recursos (iguales en las tres versiones, en la VPC por defecto de us-east-1):
- Bucket S3 privado (Block Public Access)
- EC2 `t3.micro` Amazon Linux 2023, sin IPv4 pública, IMDSv2, disco gp3 de 8 GB
- RDS PostgreSQL `db.t4g.micro`, 20 GB gp3, Single-AZ, cifrado, sin acceso público, sin backups, **contraseña administrada por RDS en Secrets Manager** (`manage_master_user_password` / `ManageMasterUserPassword` / `--manage-master-user-password`)
- Red: grupo de seguridad de la EC2 (solo salida), grupo de seguridad de RDS (5432 solo desde el SG de la EC2) y DB subnet group

## 0. Crear `user_cli` (una vez, con un usuario administrador, nunca la raíz)
```bash
AWS_PROFILE=admin uv run python punto2_terraform_sdk_cli/iam/crear_user_cli.py crear
export AWS_PROFILE=user_cli
aws sts get-caller-identity          # debe mostrar .../user/user_cli
```
El script crea el usuario y la política `iam/politica_user_cli.json`, genera la clave de acceso y la escribe **directamente** en el perfil `user_cli` de `~/.aws/credentials` (WSL) con `aws configure set`, sin mostrarla.

## 1 → 2 → 3, de forma secuencial (eliminar antes de seguir)
```bash
# Terraform
uv run python punto2_terraform_sdk_cli/terraform/ejecutar_terraform.py crear
uv run python punto2_terraform_sdk_cli/terraform/ejecutar_terraform.py eliminar
# Boto3
uv run python punto2_terraform_sdk_cli/sdk_boto3/desplegar.py crear
uv run python punto2_terraform_sdk_cli/sdk_boto3/desplegar.py eliminar
# AWS CLI
bash punto2_terraform_sdk_cli/cli/desplegar.sh crear
bash punto2_terraform_sdk_cli/cli/desplegar.sh eliminar
# Comparación y costos
uv run python punto2_terraform_sdk_cli/comparar_y_costos.py
```
Cada versión mide sus tiempos (`evidencias/punto2/tiempos.csv`) y verifica que no queden recursos.
La versión Terraform guarda la salida de `init/validate/plan/apply/output/state list/destroy` en `evidencias/punto2/terraform/` y revisa que `terraform.tfstate` no contenga contraseñas.

## Permisos de `user_cli` (`iam/politica_user_cli.json`)
| Bloque | Acciones | Para qué |
|---|---|---|
| Identidad/precios | `sts:GetCallerIdentity`, `pricing:GetProducts` | Comprobar identidad; estimar costos |
| S3 | `s3:CreateBucket`, `DeleteBucket`, `ListBucket*`, `Get*`, `PutBucketPublicAccessBlock`, `PutBucketTagging`, `PutObject`, `DeleteObject*` (solo `taller-ingdata-p2-*`) + `s3:ListAllMyBuckets` | Crear, leer (Terraform lee toda la configuración del bucket), vaciar y borrar |
| EC2 y red | `ec2:Describe*`, `RunInstances`, `TerminateInstances`, `ModifyInstanceAttribute`, `Create/DeleteSecurityGroup`, `Authorize/RevokeSecurityGroupIngress/Egress`, `Create/DeleteTags` (condición: región us-east-1) | Instancia, grupos de seguridad y consultar VPC/subredes |
| SSM | `ssm:GetParameter(s)` en `/aws/service/ami-amazon-linux-latest/*` | Obtener el AMI vigente de Amazon Linux 2023 |
| RDS | `rds:Describe*`, `ListTagsForResource`, `Add/RemoveTagsToResource`, `Create/Modify/DeleteDBInstance`, `Create/Modify/DeleteDBSubnetGroup` | Base de datos y subnet group |
| Secrets Manager | `CreateSecret`, `TagResource`, `DescribeSecret` en `secret:rds!*` | RDS crea el secreto de la contraseña **en nombre de quien llama** |
| KMS | `DescribeKey`, `CreateGrant`, `Decrypt`, `GenerateDataKey` con `kms:ViaService` = rds/secretsmanager | Cifrado del almacenamiento y del secreto |
| IAM | `iam:CreateServiceLinkedRole` solo para `AWSServiceRoleForRDS` | La primera vez que la cuenta usa RDS |

## Autenticación de `user_cli`
Las tres herramientas usan la **misma cadena de proveedores de credenciales** del SDK de AWS: variables de entorno (`AWS_ACCESS_KEY_ID`…) → perfil de `~/.aws/credentials` y `~/.aws/config` (`AWS_PROFILE=user_cli`) → SSO → metadatos de la instancia. Con la clave de acceso, cada petición se firma con **SigV4**. Terraform (proveedor `aws`) y Boto3 usan internamente el mismo mecanismo que AWS CLI, por eso basta con `export AWS_PROFILE=user_cli`. Las claves **no** pueden guardarse en Secrets Manager para que las herramientas las lean: para leer un secreto ya hay que estar autenticado en AWS (problema del huevo y la gallina).

## Estado de Terraform
`terraform.tfstate` guarda, en texto plano, todos los atributos de cada recurso: IDs, ARN, endpoints, configuración y cualquier valor sensible que se le pase (por ejemplo `password` si se escribiera en `aws_db_instance`). Con `manage_master_user_password = true` el estado solo contiene `master_user_secret` (ARN, clave KMS y estado), no la contraseña. El estado se excluye del repositorio (`.gitignore`); en equipos se usa un backend remoto cifrado (S3 + bloqueo).
