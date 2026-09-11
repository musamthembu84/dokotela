terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# =========================================================
# DATA SOURCES
# =========================================================

data "aws_availability_zones" "available" {
  state = "available"
}

# Latest Ubuntu 24.04 LTS AMI for us-east-1
data "aws_ssm_parameter" "ubuntu_ami" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

# =========================================================
# VPC
# =========================================================

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "doketela-vpc"
    Environment = "production"
  }
}

# =========================================================
# INTERNET GATEWAY
# =========================================================

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "doketela-igw"
  }
}

# =========================================================
# PUBLIC SUBNET
# =========================================================

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = {
    Name = "doketela-public-subnet"
  }
}

# =========================================================
# PRIVATE SUBNETS
# =========================================================

resource "aws_subnet" "private_1" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]

  tags = {
    Name = "doketela-private-subnet-1"
  }
}

resource "aws_subnet" "private_2" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]

  tags = {
    Name = "doketela-private-subnet-2"
  }
}

# =========================================================
# PUBLIC ROUTE TABLE
# =========================================================

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }

  tags = {
    Name = "doketela-public-route-table"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# =========================================================
# ECR - BACKEND
# =========================================================

resource "aws_ecr_repository" "dokotela" {
  name                 = "dokotela"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name        = "dokotela"
    Environment = "production"
  }
}

resource "aws_ecr_lifecycle_policy" "dokotela" {
  repository = aws_ecr_repository.dokotela.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the latest 10 images"

        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }

        action = {
          type = "expire"
        }
      }
    ]
  })
}

# =========================================================
# ECR - FRONTEND
# =========================================================

resource "aws_ecr_repository" "dokotela_frontend" {
  name                 = "dokotela-frontend"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name        = "dokotela-frontend"
    Environment = "production"
  }
}

resource "aws_ecr_lifecycle_policy" "dokotela_frontend" {
  repository = aws_ecr_repository.dokotela_frontend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the latest 10 images"

        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }

        action = {
          type = "expire"
        }
      }
    ]
  })
}

# =========================================================
# IAM ROLE FOR EC2
# =========================================================

resource "aws_iam_role" "ec2_ecr_pull" {
  name = "doketela-ec2-ecr-pull-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "ec2.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "doketela-ec2-ecr-pull-role"
  }
}

resource "aws_iam_role_policy_attachment" "ec2_ecr_pull" {
  role       = aws_iam_role.ec2_ecr_pull.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_instance_profile" "ec2_ecr_pull" {
  name = "doketela-ec2-ecr-pull-profile"
  role = aws_iam_role.ec2_ecr_pull.name
}

# =========================================================
# WEB SECURITY GROUP
# =========================================================

resource "aws_security_group" "web_sg" {
  name        = "doketela-web-sg"
  description = "Security group for Doketela application EC2"
  vpc_id      = aws_vpc.main.id

  # SSH
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # FastAPI
  ingress {
    description = "FastAPI"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Next.js frontend
  ingress {
    description = "Next.js frontend"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "doketela-web-sg"
  }
}

# =========================================================
# POSTGRESQL SECURITY GROUP
# =========================================================

resource "aws_security_group" "db_sg" {
  name        = "doketela-db-sg"
  description = "Security group for Doketela PostgreSQL"
  vpc_id      = aws_vpc.main.id

  # Direct PostgreSQL access from your Mac / IntelliJ
  #
  # Current public IP:
  # 3.230.69.18
  #
  # /32 means ONLY this IP is allowed.
  ingress {
    description = "PostgreSQL from development machine"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"

    cidr_blocks = [
      "3.230.69.18/32"
    ]
  }

  # PostgreSQL access from EC2
  ingress {
    description     = "PostgreSQL from EC2"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.web_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "doketela-db-sg"
  }
}

# =========================================================
# REDIS SECURITY GROUP
# =========================================================

resource "aws_security_group" "redis_sg" {
  name        = "doketela-redis-sg"
  description = "Security group for Doketela Redis"
  vpc_id      = aws_vpc.main.id

  # Redis is only accessible from EC2
  ingress {
    description     = "Redis from EC2"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.web_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "doketela-redis-sg"
  }
}

# =========================================================
# RDS SUBNET GROUP
# =========================================================

resource "aws_db_subnet_group" "postgres" {
  name = "doketela-postgres-subnet-group"

  subnet_ids = [
    aws_subnet.private_1.id,
    aws_subnet.private_2.id
  ]

  tags = {
    Name = "doketela-postgres-subnet-group"
  }
}

# =========================================================
# POSTGRESQL RDS
# =========================================================

resource "aws_db_instance" "postgres" {
  identifier = "doketela-db"

  engine         = "postgres"
  engine_version = "17"

  instance_class        = "db.t4g.micro"
  allocated_storage     = 20
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "postgres"
  username = "db_admin_musa"
  password = var.db_password

  port = 5432

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.db_sg.id]

  # Allows direct connection from IntelliJ/DataGrip.
  # Security group restricts access to 3.230.69.18.
  publicly_accessible = true

  backup_retention_period = 0

  skip_final_snapshot = true
  deletion_protection = false

  tags = {
    Name        = "doketela-db"
    Environment = "production"
  }
}

# =========================================================
# REDIS SUBNET GROUP
# =========================================================

resource "aws_elasticache_subnet_group" "redis" {
  name = "doketela-redis-subnet-group"

  subnet_ids = [
    aws_subnet.private_1.id,
    aws_subnet.private_2.id
  ]
}

# =========================================================
# REDIS
# =========================================================

resource "aws_elasticache_cluster" "redis" {
  cluster_id = "doketela-redis"

  engine         = "redis"
  engine_version = "7.1"

  node_type = "cache.t4g.micro"

  num_cache_nodes = 1
  port            = 6379

  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis_sg.id]

  tags = {
    Name        = "doketela-redis"
    Environment = "production"
  }
}

# =========================================================
# EC2 SSH KEY
# =========================================================

resource "aws_key_pair" "deployer" {
  key_name   = "doketela-deployer-key"
  public_key = file(pathexpand("~/.ssh/id_ed25519.pub"))

  tags = {
    Name = "doketela-deployer-key"
  }
}

# =========================================================
# EC2
# =========================================================

resource "aws_instance" "web" {
  ami           = data.aws_ssm_parameter.ubuntu_ami.value
  instance_type = "t3.micro"

  subnet_id = aws_subnet.public.id

  vpc_security_group_ids = [
    aws_security_group.web_sg.id
  ]

  key_name = aws_key_pair.deployer.key_name

  # EC2 uses IAM role to pull from ECR.
  # No AWS credentials are stored on the server.
  iam_instance_profile = aws_iam_instance_profile.ec2_ecr_pull.name

  user_data = <<-EOF
    #!/bin/bash

    set -e

    export DEBIAN_FRONTEND=noninteractive

    # Update Ubuntu
    apt-get update -y

    # Install Docker and supporting tools
    apt-get install -y \
      docker.io \
      docker-compose-v2 \
      curl \
      unzip

    # Start Docker
    systemctl enable docker
    systemctl start docker

    # Allow ubuntu user to use Docker
    usermod -aG docker ubuntu

    # Application directory
    mkdir -p /home/ubuntu/app

    # Correct ownership
    chown -R ubuntu:ubuntu /home/ubuntu/app

    # Restart Docker
    systemctl restart docker
  EOF

  tags = {
    Name        = "Doketela-Docker-Server"
    Environment = "production"
  }
}

# =========================================================
# ELASTIC IP
# =========================================================

resource "aws_eip" "doketela_static_ip" {
  domain   = "vpc"
  instance = aws_instance.web.id

  tags = {
    Name = "doketela-static-ip"
  }
}