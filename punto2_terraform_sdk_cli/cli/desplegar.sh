#!/usr/bin/env bash
# Punto 2 - Versión AWS CLI (bash, p. ej. Ubuntu en WSL). Mismos recursos que Terraform y Boto3.
#
#   export AWS_PROFILE=user_cli
#   bash punto2_terraform_sdk_cli/cli/desplegar.sh crear
#   bash punto2_terraform_sdk_cli/cli/desplegar.sh eliminar
#
# Todos los comandos y sus respuestas quedan en evidencias/punto2/cli/cli_<accion>.log
set -euo pipefail

ACCION="${1:?Uso: desplegar.sh crear|eliminar}"
REGION="${AWS_REGION:-us-east-1}"
PREFIJO="taller-ingdata-p2-cli"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIR_EV="$RAIZ/evidencias/punto2/cli"
ESTADO="$RAIZ/.estado/punto2_cli.env"
TIEMPOS="$RAIZ/evidencias/punto2/tiempos.csv"
mkdir -p "$DIR_EV" "$RAIZ/.estado"
LOG="$DIR_EV/cli_${ACCION}.log"
export AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""

# Ejecuta aws, registra comando + salida en el log y devuelve la salida
aws_() {
  echo -e "\n\$ aws $*" >> "$LOG"
  echo -e "\033[36m\$ aws $*\033[0m" >&2
  local salida err
  err=$(mktemp)
  if ! salida=$(aws "$@" --region "$REGION" 2>"$err"); then
    cat "$err" | tee -a "$LOG" >&2
    rm -f "$err"
    echo "FALLÓ: aws $*" >&2
    exit 1
  fi
  cat "$err" >> "$LOG"; rm -f "$err"
  echo "$salida" >> "$LOG"
  [ -n "$salida" ] && echo "$salida" >&2
  echo "$salida"
}

# Igual pero sin abortar (para verificar la eliminación)
probar_() {
  local salida
  salida=$(aws "$@" --region "$REGION" 2>&1) || true
  echo -e "\n\$ aws $*\n$salida" >> "$LOG"
  echo "$salida"
}

registrar_tiempo() {
  [ -f "$TIEMPOS" ] || echo "fecha,metodo,accion,segundos" > "$TIEMPOS"
  echo "$(date +%Y-%m-%dT%H:%M:%S),cli,$1,$2" >> "$TIEMPOS"
}

echo -e "\n===== $ACCION $(date -Is) =====" >> "$LOG"
INICIO=$(date +%s)

if [ "$ACCION" = "crear" ]; then
  CUENTA=$(aws_ sts get-caller-identity --query Account --output text)
  aws_ sts get-caller-identity --output json > /dev/null
  BUCKET="$PREFIJO-$CUENTA"

  # --- S3 (privado)
  if [ "$REGION" = "us-east-1" ]; then
    aws_ s3api create-bucket --bucket "$BUCKET" > /dev/null
  else
    aws_ s3api create-bucket --bucket "$BUCKET" \
      --create-bucket-configuration "LocationConstraint=$REGION" > /dev/null
  fi
  aws_ s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" > /dev/null

  # --- Red: VPC por defecto y subredes
  VPC=$(aws_ ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text)
  read -r -a SUBREDES <<< "$(aws_ ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC" \
    --query "Subnets[].SubnetId" --output text)"

  # --- Grupos de seguridad
  SG_EC2=$(aws_ ec2 create-security-group --group-name "$PREFIJO-ec2-sg" \
    --description "EC2 del taller sin entradas" --vpc-id "$VPC" --query GroupId --output text)
  SG_RDS=$(aws_ ec2 create-security-group --group-name "$PREFIJO-rds-sg" \
    --description "RDS 5432 solo desde la EC2" --vpc-id "$VPC" --query GroupId --output text)
  aws_ ec2 authorize-security-group-ingress --group-id "$SG_RDS" --protocol tcp --port 5432 \
    --source-group "$SG_EC2" > /dev/null

  # --- EC2 (sin IPv4 pública: se cobra 0,005 USD/h)
  AMI=$(aws_ ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
    --query Parameter.Value --output text)
  EC2=$(aws_ ec2 run-instances --image-id "$AMI" --instance-type t3.micro --count 1 \
    --network-interfaces "DeviceIndex=0,SubnetId=${SUBREDES[0]},Groups=$SG_EC2,AssociatePublicIpAddress=false" \
    --metadata-options "HttpTokens=required" \
    --block-device-mappings "DeviceName=/dev/xvda,Ebs={VolumeSize=8,VolumeType=gp3,DeleteOnTermination=true}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$PREFIJO-ec2},{Key=proyecto,Value=taller-ingdata}]" \
    --query "Instances[0].InstanceId" --output text)

  # --- RDS (contraseña administrada por RDS en Secrets Manager)
  aws_ rds create-db-subnet-group --db-subnet-group-name "$PREFIJO-subnets" \
    --db-subnet-group-description "Subredes VPC por defecto" --subnet-ids "${SUBREDES[@]}" > /dev/null
  aws_ rds create-db-instance --db-instance-identifier "$PREFIJO-rds" --engine postgres \
    --db-instance-class db.t4g.micro --allocated-storage 20 --storage-type gp3 --storage-encrypted \
    --master-username dbadmin --manage-master-user-password \
    --db-subnet-group-name "$PREFIJO-subnets" --vpc-security-group-ids "$SG_RDS" \
    --no-publicly-accessible --no-multi-az --backup-retention-period 0 --no-deletion-protection \
    --tags "Key=proyecto,Value=taller-ingdata" --query DBInstance.DBInstanceStatus --output text > /dev/null

  printf 'BUCKET=%q\nSG_EC2=%q\nSG_RDS=%q\nEC2=%q\n' "$BUCKET" "$SG_EC2" "$SG_RDS" "$EC2" > "$ESTADO"

  echo "Esperando EC2 y RDS (5-10 min)..." >&2
  aws_ ec2 wait instance-running --instance-ids "$EC2" > /dev/null
  aws_ rds wait db-instance-available --db-instance-identifier "$PREFIJO-rds" > /dev/null

  SECRETO=$(aws_ rds describe-db-instances --db-instance-identifier "$PREFIJO-rds" \
    --query "DBInstances[0].MasterUserSecret.SecretArn" --output text)
  aws_ rds describe-db-instances --db-instance-identifier "$PREFIJO-rds" --query \
    "DBInstances[0].{Id:DBInstanceIdentifier,Estado:DBInstanceStatus,Clase:DBInstanceClass,Endpoint:Endpoint.Address,Secreto:MasterUserSecret}" \
    --output json > /dev/null
  aws_ ec2 describe-instances --instance-ids "$EC2" --query \
    "Reservations[0].Instances[0].{Id:InstanceId,Tipo:InstanceType,Estado:State.Name,IPPrivada:PrivateIpAddress,IPPublica:PublicIpAddress}" \
    --output json > /dev/null
  printf 'SECRETO=%q\n' "$SECRETO" >> "$ESTADO"
  SEG=$(( $(date +%s) - INICIO ))
  registrar_tiempo crear "$SEG"
  echo "Creación terminada en ${SEG} s" >&2

else
  # shellcheck disable=SC1090
  source "$ESTADO"
  aws_ rds delete-db-instance --db-instance-identifier "$PREFIJO-rds" --skip-final-snapshot \
    --delete-automated-backups --query DBInstance.DBInstanceStatus --output text > /dev/null
  aws_ ec2 terminate-instances --instance-ids "$EC2" > /dev/null
  aws_ ec2 wait instance-terminated --instance-ids "$EC2" > /dev/null
  aws_ rds wait db-instance-deleted --db-instance-identifier "$PREFIJO-rds" > /dev/null
  aws_ rds delete-db-subnet-group --db-subnet-group-name "$PREFIJO-subnets" > /dev/null
  for SG in "$SG_RDS" "$SG_EC2"; do
    for _ in $(seq 10); do
      R=$(probar_ ec2 delete-security-group --group-id "$SG")
      echo "$R" | grep -q DependencyViolation || break
      sleep 20
    done
  done
  aws_ s3 rb "s3://$BUCKET" --force > /dev/null
  registrar_tiempo eliminar $(( $(date +%s) - INICIO ))

  # --- Verificación: cada consulta debe responder "no encontrado", vacío o terminated
  echo -e "\n----- VERIFICACIÓN DE ELIMINACIÓN -----" >> "$LOG"
  {
    echo "Bucket: $(probar_ s3api head-bucket --bucket "$BUCKET")"
    echo "EC2: $(probar_ ec2 describe-instances --instance-ids "$EC2" --query 'Reservations[0].Instances[0].State.Name' --output text)"
    echo "RDS: $(probar_ rds describe-db-instances --db-instance-identifier "$PREFIJO-rds")"
    echo "Subnet group: $(probar_ rds describe-db-subnet-groups --db-subnet-group-name "$PREFIJO-subnets")"
    echo "SGs restantes: $(probar_ ec2 describe-security-groups --filters "Name=group-name,Values=$PREFIJO*" --query 'SecurityGroups[].GroupId' --output text)"
    [ -n "${SECRETO:-}" ] && echo "Secreto RDS (DeletedDate): $(probar_ secretsmanager describe-secret --secret-id "$SECRETO" --query DeletedDate --output text)"
  } | tee "$DIR_EV/cli_verificacion_eliminacion.txt"
  rm -f "$ESTADO"
fi
