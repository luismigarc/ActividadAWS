variable "region" {
  description = "Región única del taller"
  type        = string
  default     = "us-east-1"
}

variable "perfil_aws" {
  description = "Perfil de AWS CLI con las claves de user_cli"
  type        = string
  default     = "user_cli"
}

variable "prefijo" {
  description = "Prefijo de nombres de los recursos"
  type        = string
  default     = "taller-ingdata-p2-tf"
}

variable "tipo_instancia" {
  description = "Tipo de EC2 de menor costo (capa gratuita)"
  type        = string
  default     = "t3.micro"
}

variable "clase_rds" {
  description = "Clase de RDS de menor costo (capa gratuita)"
  type        = string
  default     = "db.t4g.micro"
}
