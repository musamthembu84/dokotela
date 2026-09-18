terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Local state, applied manually from your machine (as today). After
  # `terraform apply`, run `terraform/sync-outputs-to-github-secrets.sh` to
  # push the real Redis/RDS endpoints, EC2 IP and ECR URLs into GitHub
  # Actions secrets so the deploy workflow never has them hand-typed.
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
    Name        = "${var.project_name}-vpc"
    Environment = "production"
  }
}

# =========================================================
# INTERNET GATEWAY
# =========================================================

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
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
    Name = "${var.project_name}-public-subnet"
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
    Name = "${var.project_name}-private-subnet-1"
  }
}

resource "aws_subnet" "private_2" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]

  tags = {
    Name = "${var.project_name}-private-subnet-2"
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
    Name = "${var.project_name}-public-route-table"
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
  name                 = var.project_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name        = var.project_name
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
  name                 = "${var.project_name}-frontend"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name        = "${var.project_name}-frontend"
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
#
# Scoped to exactly what the instance needs at runtime:
#  - Pull images from ECR (managed, read-only policy)
#  - Write its own Docker/Nginx/Certbot logs to CloudWatch (optional, least
#    privilege) so "EC2 couldn't run some AWS CLI commands" never recurs
#    silently - failures are visible in CloudWatch instead of only on SSH.
# No broad admin/EC2-wide permissions are granted.

resource "aws_iam_role" "ec2_ecr_pull" {
  name = "${var.project_name}-ec2-ecr-pull-role"

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
    Name = "${var.project_name}-ec2-ecr-pull-role"
  }
}

resource "aws_iam_role_policy_attachment" "ec2_ecr_pull" {
  role       = aws_iam_role.ec2_ecr_pull.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy" "ec2_cloudwatch_logs" {
  name = "${var.project_name}-ec2-cloudwatch-logs"
  role = aws_iam_role.ec2_ecr_pull.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:log-group:/${var.project_name}/*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "ec2_ecr_pull" {
  name = "${var.project_name}-ec2-ecr-pull-profile"
  role = aws_iam_role.ec2_ecr_pull.name
}

# =========================================================
# WEB SECURITY GROUP
# =========================================================
#
# Only SSH, HTTP and HTTPS are exposed publicly. The application ports
# (3000/8000) are never opened to the internet - Nginx (installed via
# user_data) terminates TLS and reverse-proxies to the containers on
# localhost. This closes the "application exposed directly on :3000/:8000"
# gap.

resource "aws_security_group" "web_sg" {
  name        = "${var.project_name}-web-sg"
  description = "Security group for ${var.project_name} application EC2"
  vpc_id      = aws_vpc.main.id

  # SSH
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # HTTP (redirects to HTTPS once Nginx/Certbot are configured)
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
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
    Name = "${var.project_name}-web-sg"
  }
}

# =========================================================
# POSTGRESQL SECURITY GROUP
# =========================================================

resource "aws_security_group" "db_sg" {
  name        = "${var.project_name}-db-sg"
  description = "Security group for ${var.project_name} PostgreSQL"
  vpc_id      = aws_vpc.main.id

  # Direct PostgreSQL access from your Mac / IntelliJ.
  # var.dev_machine_cidr must be a /32 of your current public IP.
  ingress {
    description = "PostgreSQL from development machine"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"

    cidr_blocks = [
      var.dev_machine_cidr
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
    Name = "${var.project_name}-db-sg"
  }
}

# =========================================================
# REDIS SECURITY GROUP
# =========================================================

resource "aws_security_group" "redis_sg" {
  name        = "${var.project_name}-redis-sg"
  description = "Security group for ${var.project_name} Redis"
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
    Name = "${var.project_name}-redis-sg"
  }
}

# =========================================================
# RDS SUBNET GROUP
# =========================================================

resource "aws_db_subnet_group" "postgres" {
  name = "${var.project_name}-postgres-subnet-group"

  subnet_ids = [
    aws_subnet.private_1.id,
    aws_subnet.private_2.id
  ]

  tags = {
    Name = "${var.project_name}-postgres-subnet-group"
  }
}

# =========================================================
# POSTGRESQL RDS
# =========================================================

resource "aws_db_instance" "postgres" {
  identifier = "${var.project_name}-db"

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
  # Security group restricts access to var.dev_machine_cidr.
  publicly_accessible = true

  backup_retention_period = 0

  skip_final_snapshot = true
  deletion_protection = false

  tags = {
    Name        = "${var.project_name}-db"
    Environment = "production"
  }
}

# =========================================================
# REDIS SUBNET GROUP
# =========================================================

resource "aws_elasticache_subnet_group" "redis" {
  name = "${var.project_name}-redis-subnet-group"

  subnet_ids = [
    aws_subnet.private_1.id,
    aws_subnet.private_2.id
  ]
}

# =========================================================
# REDIS
# =========================================================
#
# aws_vpc.main has enable_dns_hostnames/enable_dns_support = true, which is
# required for the ElastiCache-managed DNS name (cache_nodes[0].address) to
# resolve from the EC2 instance. Consumers must use the
# `redis_endpoint` Terraform output below rather than typing/guessing the
# hostname, which is what caused the doketela/dokotela DNS mismatch.

resource "aws_elasticache_cluster" "redis" {
  cluster_id = "${var.project_name}-redis"

  engine         = "redis"
  engine_version = "7.1"

  node_type = "cache.t4g.micro"

  num_cache_nodes = 1
  port            = 6379

  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis_sg.id]

  tags = {
    Name        = "${var.project_name}-redis"
    Environment = "production"
  }
}

# =========================================================
# EC2 SSH KEY
# =========================================================

resource "aws_key_pair" "deployer" {
  key_name   = "${var.project_name}-deployer-key"
  public_key = file(pathexpand("~/.ssh/id_ed25519.pub"))

  tags = {
    Name = "${var.project_name}-deployer-key"
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

  # Bootstraps everything the instance needs so nothing has to be configured
  # by hand over SSH after launch:
  #  - Docker + Docker Compose plugin
  #  - AWS CLI v2 (previously missing - this is why "EC2 couldn't run some
  #    AWS CLI commands" such as `aws ecr get-login-password` during deploy)
  #  - Nginx + Certbot for HTTPS termination in front of the app containers
  #  - Docker log rotation so disks don't fill up while debugging
  user_data = <<-EOF
    #!/bin/bash

    set -e

    export DEBIAN_FRONTEND=noninteractive

    exec > >(tee /var/log/dokotela-bootstrap.log) 2>&1

    # Update Ubuntu
    apt-get update -y

    # Install Docker, AWS CLI prerequisites, and Nginx/Certbot
    apt-get install -y \
      docker.io \
      docker-compose-v2 \
      curl \
      unzip \
      nginx \
      certbot \
      python3-certbot-nginx

    # Install AWS CLI v2 (required so the deploy script can run
    # `aws ecr get-login-password` on this host)
    curl -sS "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip"
    unzip -q -o /tmp/awscliv2.zip -d /tmp
    /tmp/aws/install --update
    rm -rf /tmp/awscliv2.zip /tmp/aws

    # Start Docker
    systemctl enable docker
    systemctl start docker

    # Rotate Docker container logs so a long-running debug session doesn't
    # fill up the disk
    cat <<'DOCKERJSON' > /etc/docker/daemon.json
    {
      "log-driver": "json-file",
      "log-opts": {
        "max-size": "10m",
        "max-file": "3"
      }
    }
    DOCKERJSON

    # Allow ubuntu user to use Docker
    usermod -aG docker ubuntu

    # Application directory
    mkdir -p /home/ubuntu/app
    chown -R ubuntu:ubuntu /home/ubuntu/app

    # Ensure the ubuntu user's SSH directory exists with correct
    # permissions before any deploy tooling tries to write to it
    mkdir -p /home/ubuntu/.ssh
    chmod 700 /home/ubuntu/.ssh
    chown -R ubuntu:ubuntu /home/ubuntu/.ssh

    # Restart Docker to pick up the log-driver config
    systemctl restart docker

    # Basic Nginx reverse proxy in front of the FastAPI container.
    # HTTP is served immediately; HTTPS is enabled below once a domain is
    # configured and DNS has propagated.
    cat <<'NGINXCONF' > /etc/nginx/sites-available/${var.project_name}
    server {
        listen 80;
        server_name ${var.domain_name != "" ? var.domain_name : "_"};

        location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    NGINXCONF

    rm -f /etc/nginx/sites-enabled/default
    ln -sf /etc/nginx/sites-available/${var.project_name} /etc/nginx/sites-enabled/${var.project_name}
    nginx -t && systemctl restart nginx
    systemctl enable nginx

    %{if var.domain_name != "" && var.admin_email != ""}
    # Obtain/renew the HTTPS certificate. Wrapped in `|| true` because DNS
    # for a brand new Elastic IP may not have propagated yet at boot time;
    # certbot can be re-run manually (or via its systemd timer) once it has.
    certbot --nginx \
      --non-interactive \
      --agree-tos \
      -m "${var.admin_email}" \
      -d "${var.domain_name}" \
      --redirect || true
    %{endif}
  EOF

  tags = {
    Name        = "${var.project_name}-docker-server"
    Environment = "production"
  }
}

# =========================================================
# ELASTIC IP
# =========================================================

resource "aws_eip" "dokotela_static_ip" {
  domain   = "vpc"
  instance = aws_instance.web.id

  tags = {
    Name = "${var.project_name}-static-ip"
  }
}
