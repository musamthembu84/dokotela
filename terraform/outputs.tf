output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "ec2_public_ip" {
  description = "Dokotela EC2 public (Elastic) IP. Deployment automation must consume this output rather than a manually copied value."
  value       = aws_eip.dokotela_static_ip.public_ip
}

output "ec2_public_dns" {
  description = "Dokotela EC2 public DNS"
  value       = aws_instance.web.public_dns
}

output "ecr_backend_repository_url" {
  description = "Backend ECR repository"
  value       = aws_ecr_repository.dokotela.repository_url
}

output "ecr_frontend_repository_url" {
  description = "Frontend ECR repository"
  value       = aws_ecr_repository.dokotela_frontend.repository_url
}

output "rds_endpoint" {
  description = "PostgreSQL RDS endpoint (hostname only, no port). Deployment automation must consume this output rather than typing it manually."
  value       = aws_db_instance.postgres.address
}

output "rds_port" {
  description = "PostgreSQL RDS port"
  value       = aws_db_instance.postgres.port
}

output "redis_endpoint" {
  description = "Redis endpoint (hostname only, no port). Deployment automation must consume this output rather than typing it manually - this is what caused the doketela/dokotela DNS mismatch."
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "redis_port" {
  description = "Redis port"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].port
}

output "app_url" {
  description = "Public URL of the deployed application (HTTPS if domain_name/admin_email are set, otherwise plain HTTP over the Elastic IP)."
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${aws_eip.dokotela_static_ip.public_ip}"
}

output "destroy_command" {
  description = "Reminder: tear this environment down when not actively deploying/debugging to avoid unnecessary AWS costs."
  value       = "terraform destroy -var=\"db_password=<value>\""
}
