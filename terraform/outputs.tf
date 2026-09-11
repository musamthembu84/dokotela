output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "ec2_public_ip" {
  description = "Doketela EC2 public IP"
  value       = aws_eip.doketela_static_ip.public_ip
}

output "ec2_public_dns" {
  description = "Doketela EC2 public DNS"
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
  description = "PostgreSQL RDS endpoint"
  value       = aws_db_instance.postgres.address
}

output "redis_endpoint" {
  description = "Redis endpoint"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}