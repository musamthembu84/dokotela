variable "project_name" {
  description = "Canonical project name used as a prefix for all Dokotela resource names/tags. Single source of truth to avoid naming drift (e.g. dokotela vs doketela)."
  type        = string
  default     = "dokotela"
}

variable "aws_region" {
  description = "AWS region where Dokotela infrastructure will be deployed"
  type        = string
  default     = "us-east-1"
}

variable "db_password" {
  description = "Password for the Dokotela PostgreSQL database. Pass via TF_VAR_db_password or -var, never commit to source control."
  type        = string
  sensitive   = true
}

variable "dev_machine_cidr" {
  description = "CIDR block (your current public IP, /32) allowed direct PostgreSQL access for local development tools (DataGrip/IntelliJ)."
  type        = string
  default     = "3.230.69.18/32"
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed to SSH into the EC2 instance. Restrict this to your office/VPN IP in production."
  type        = string
  default     = "0.0.0.0/0"
}

variable "domain_name" {
  description = "Public domain name pointed at the EC2 Elastic IP (e.g. api.dokotela.com). When set, the bootstrap script provisions an Nginx + Let's Encrypt HTTPS reverse proxy. Leave empty to skip HTTPS provisioning."
  type        = string
  default     = ""
}

variable "admin_email" {
  description = "Email address used for Let's Encrypt certificate registration/renewal notices. Required when domain_name is set."
  type        = string
  default     = ""
}
