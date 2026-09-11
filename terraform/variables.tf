variable "aws_region" {
  description = "AWS region where Doketela infrastructure will be deployed"
  type        = string
  default     = "us-east-1"
}

variable "db_password" {
  description = "Password for the Doketela PostgreSQL database"
  type        = string
  sensitive   = true
}