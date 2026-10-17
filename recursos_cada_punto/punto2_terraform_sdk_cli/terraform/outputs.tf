output "bucket" {
  value = aws_s3_bucket.datos.bucket
}

output "ec2_id" {
  value = aws_instance.app.id
}

output "rds_endpoint" {
  value = aws_db_instance.bd.address
}

output "rds_identificador" {
  value = aws_db_instance.bd.identifier
}

# Solo el ARN del secreto (no su valor)
output "rds_secreto_arn" {
  value = aws_db_instance.bd.master_user_secret[0].secret_arn
}

output "security_groups" {
  value = [aws_security_group.ec2.id, aws_security_group.rds.id]
}
