variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "private_ip" {
  description = "IP privado fixo da EC2 (subnet app-1). Contrato com o repo infra: otel_endpoint_ip."
  type        = string
  default     = "10.0.2.120"
}

variable "instance_type" {
  description = "t3.medium não comporta ~4,75 GB de limites; t3.xlarge é negada no lab"
  type        = string
  default     = "t3.large"
}

variable "ami_id" {
  description = "Mesma AMI das EC2 de app (repo infra)"
  type        = string
  default     = "ami-0521cb2d60cfbb1a6"
}

variable "key_name" {
  type    = string
  default = "chave"
}

variable "private_key_path" {
  description = "Chave SSH, relativa à pasta ansible/"
  type        = string
  default     = "../../DevOps/prod/terraform/chave.pem"
}
