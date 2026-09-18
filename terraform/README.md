# Dokotela Terraform

## One-time backend bootstrap (before first `terraform init`)

State is stored remotely in S3 (with DynamoDB locking) so CI/CD can reliably
run `terraform output` and consume real infrastructure values instead of
engineers manually copy-pasting endpoints/IPs into GitHub Secrets.

```bash
aws s3api create-bucket --bucket dokotela-terraform-state --region us-east-1
aws s3api put-bucket-versioning --bucket dokotela-terraform-state \
  --versioning-configuration Status=Enabled

aws dynamodb create-table --table-name dokotela-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

## Init / plan / apply

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in real values, never commit it

terraform init \
  -backend-config="bucket=dokotela-terraform-state" \
  -backend-config="key=dokotela/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=dokotela-terraform-locks"

terraform plan
terraform apply
```

Prefer `TF_VAR_db_password` (and `TF_VAR_domain_name`, `TF_VAR_admin_email`)
environment variables over putting secrets in `terraform.tfvars`.

## Consuming outputs (never type endpoints manually)

```bash
terraform output -raw redis_endpoint
terraform output -raw rds_endpoint
terraform output -raw ec2_public_ip
terraform output -raw ecr_backend_repository_url
```

The GitHub Actions deploy workflow (`.github/workflows/deploy.yml`) runs
`terraform apply` and reads these outputs directly, so the Redis/RDS
hostnames and EC2 IP used at deploy time are always the real Terraform-owned
values.

## HTTPS

Set `domain_name` and `admin_email` in `terraform.tfvars` (and point the
domain's DNS A record at the `ec2_public_ip` output). The EC2 bootstrap
script installs Nginx + Certbot and requests a Let's Encrypt certificate
automatically. Application ports 3000/8000 are not exposed publicly - only
22/80/443 are open in the security group.

## Tearing down to control cost

```bash
terraform destroy
```

Since state is remote, `destroy`/`apply` can be run repeatably without
losing track of what's deployed - spin the environment up for a deploy or
debugging session and tear it down afterwards.
