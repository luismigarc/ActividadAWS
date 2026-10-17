terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40"
    }
  }
}

# La autenticación NO está en el código: el proveedor usa la cadena de credenciales
# estándar de AWS (variables de entorno o el perfil `user_cli` de ~/.aws/credentials).
provider "aws" {
  region  = var.region
  profile = var.perfil_aws

  default_tags {
    tags = {
      proyecto = "taller-ingdata"
      metodo   = "terraform"
    }
  }
}
