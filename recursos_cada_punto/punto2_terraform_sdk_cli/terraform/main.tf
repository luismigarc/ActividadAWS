data "aws_caller_identity" "actual" {}

# ---------------------------------------------------------------- red existente
# Se usa la VPC por defecto (sin NAT Gateway ni VPC nuevas: costo cero).
data "aws_vpc" "defecto" {
  default = true
}

data "aws_subnets" "defecto" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.defecto.id]
  }
}

# AMI pública de Amazon Linux 2023 publicada por AWS en SSM Parameter Store
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# ---------------------------------------------------------------- S3
resource "aws_s3_bucket" "datos" {
  bucket        = "${var.prefijo}-${data.aws_caller_identity.actual.account_id}"
  force_destroy = true # permite destroy aunque tenga objetos
}

resource "aws_s3_bucket_public_access_block" "datos" {
  bucket                  = aws_s3_bucket.datos.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------- grupos de seguridad
resource "aws_security_group" "ec2" {
  name        = "${var.prefijo}-ec2-sg"
  description = "EC2 del taller: sin entradas, solo salida"
  vpc_id      = data.aws_vpc.defecto.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.prefijo}-rds-sg"
  description = "RDS del taller: PostgreSQL solo desde el SG de la EC2"
  vpc_id      = data.aws_vpc.defecto.id

  ingress {
    description     = "PostgreSQL desde la EC2"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2.id]
  }
}

# ---------------------------------------------------------------- EC2
resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.al2023.insecure_value
  instance_type          = var.tipo_instancia
  subnet_id              = sort(data.aws_subnets.defecto.ids)[0]
  vpc_security_group_ids = [aws_security_group.ec2.id]

  # Sin IPv4 pública: AWS cobra 0,005 USD/h por cada IPv4 pública
  associate_public_ip_address = false

  metadata_options {
    http_tokens = "required" # IMDSv2
  }

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
  }

  tags = {
    Name = "${var.prefijo}-ec2"
  }
}

# ---------------------------------------------------------------- RDS
resource "aws_db_subnet_group" "rds" {
  name       = "${var.prefijo}-subnets"
  subnet_ids = data.aws_subnets.defecto.ids
}

resource "aws_db_instance" "bd" {
  identifier     = "${var.prefijo}-rds"
  engine         = "postgres"
  instance_class = var.clase_rds

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  username = "dbadmin"
  # La contraseña la genera RDS y la guarda en Secrets Manager.
  # Así NO aparece en el código ni en el archivo de estado de Terraform.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.rds.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period = 0    # sin backups automáticos (sin costo extra)
  skip_final_snapshot     = true # destroy sin snapshot final
  deletion_protection     = false
  apply_immediately       = true
}
