provider "aws" {
  region = "us-east-1"
}

# ==============================================================================
# 1. NETWORK LAYER (VPC, Subnets & Routing)
# ==============================================================================

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags                 = { Name = "fastapi-vpc" }
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "fastapi-igw" }
}

# Public Subnet for the EC2 Application Server
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "us-east-1a"
  tags                    = { Name = "fastapi-public-subnet" }
}

# Private Subnet 1 for Managed Data Services (Fixed CIDR Block Conflict)
resource "aws_subnet" "private_1" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24" # Changed from 10.0.1.0/24 to prevent overlap
  availability_zone = "us-east-1a"
  tags              = { Name = "fastapi-private-subnet-1" }
}

# Private Subnet 2 for Managed Data Services (Required for Multi-AZ RDS Deployment)
resource "aws_subnet" "private_2" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "us-east-1b"
  tags              = { Name = "fastapi-private-subnet-2" }
}

# Public Routing Configurations
resource "aws_route_table" "rt" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }
}

resource "aws_route_table_association" "a" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.rt.id
}

# ==============================================================================
# 2. FIREWALL & SECURITY GROUPS
# ==============================================================================

# Security Group for the EC2 Web Server
resource "aws_security_group" "web_sg" {
  name        = "fastapi-sg"
  description = "Allow inbound SSH and HTTP traffic to FastAPI server"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # Restrict to your specific home IP address later!
  }

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Security Group for the PostgreSQL Database
resource "aws_security_group" "db_sg" {
  name        = "fastapi-db-sg"
  description = "Allow inbound Postgres traffic strictly from the EC2 web server"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.web_sg.id] # Only the EC2 instance can reach RDS
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Security Group for the Redis Cache Cluster
resource "aws_security_group" "redis_sg" {
  name        = "fastapi-redis-sg"
  description = "Allow inbound Redis traffic strictly from the EC2 web server"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.web_sg.id] # Only the EC2 instance can reach Redis
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ==============================================================================
# 3. DATA SUBNET CLUSTERS & STORAGE PROVISIONS
# ==============================================================================

# Database Placement Configuration
resource "aws_db_subnet_group" "db_subnets" {
  name       = "fastapi-db-subnet-group"
  subnet_ids = [aws_subnet.private_1.id, aws_subnet.private_2.id]
  tags       = { Name = "DB Subnet Group" }
}

# Managed AWS RDS PostgreSQL Database Instance
resource "aws_db_instance" "postgres" {
  identifier             = "dokotela-db"
  engine                 = "postgres"
  engine_version         = "17"
  instance_class         = "db.t4g.micro"
  allocated_storage      = 20
  db_name                = "postgres"
  username               = "db_admin_musa"
  password               = var.db_password # References the secure runtime variable
  db_subnet_group_name   = aws_db_subnet_group.db_subnets.name
  vpc_security_group_ids = [aws_security_group.db_sg.id]
  publicly_accessible    = false # Hidden from the open internet
  skip_final_snapshot    = true
}

# Redis Placement Configuration
resource "aws_elasticache_subnet_group" "redis_subnets" {
  name       = "fastapi-redis-subnet-group"
  subnet_ids = [aws_subnet.private_1.id, aws_subnet.private_2.id]
}

# Managed AWS ElastiCache for Redis Cluster
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "dokotela-redis"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.0"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis_subnets.name
  security_group_ids   = [aws_security_group.redis_sg.id]
}

# ==============================================================================
# 4. COMPUTE & APPLICATION LAYER
# ==============================================================================

resource "aws_key_pair" "deployer" {
  key_name   = "fastapi-deployer-key"
  public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIN2s06z4E5hpqSk3i+v6iaXLyeWSgKQoM85o2yoKUz7s musamthembu84@gmail.com"
}

# EC2 Instance with Automated Bootstrapping Configuration
resource "aws_instance" "web" {
  ami                    = "ami-0c7217cdde317cfec" # Valid updated Amazon Linux 2023 AMI for us-east-1
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web_sg.id]
  key_name               = aws_key_pair.deployer.key_name # Fixed resource reference tracking string

  user_data = <<-EOF
              #!/bin/bash
              dnf update -y
              dnf install -y docker
              systemctl start docker
              systemctl enable docker
              usermod -aG docker ec2-user

              # Install Docker Compose V2
              mkdir -p /usr/local/lib/docker/cli-plugins/
              curl -SL https://github.com -o /usr/local/lib/docker/cli-plugins/docker-compose
              chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

              mkdir -p /home/ec2-user/app
              chown -R ec2-user:ec2-user /home/ec2-user/app
              EOF

  tags = { Name = "FastAPI-Docker-Server" }
}

# ==============================================================================
# 5. VARIABLES & OUTBOUND OUTPUT STRINGS
# ==============================================================================

variable "db_password" {
  type      = string
  sensitive = true
}

output "public_ip" {
  value       = aws_instance.web.public_ip
  description = "The public IP of your FastAPI server"
}

output "rds_endpoint" {
  value       = aws_db_instance.postgres.endpoint
  description = "The connection endpoint string for your RDS instance"
}

output "redis_endpoint" {
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
  description = "The network connection address for your Redis cluster"
}
