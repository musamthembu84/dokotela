# Dokotela Terraform

State is local (like today) - applied manually from your machine, no S3
bucket or remote backend required.

## Init / plan / apply

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in real values, never commit it

terraform init
terraform plan
terraform apply
```

Prefer `TF_VAR_db_password` (and `TF_VAR_domain_name`, `TF_VAR_admin_email`)
environment variables over putting secrets into `terraform.tfvars`.

## Syncing outputs to GitHub Actions (never type endpoints manually)

After every `terraform apply`, run:

```bash
./sync-outputs-to-github-secrets.sh
```

This reads `terraform output` directly and pushes the real values into
GitHub Actions secrets via the `gh` CLI:

| Secret                         | Terraform output               |
|---------------------------------|---------------------------------|
| `EC2_PUBLIC_IP`                  | `ec2_public_ip`                 |
| `AWS_RDS_ENDPOINT`               | `rds_endpoint`                   |
| `AWS_REDIS_ENDPOINT`             | `redis_endpoint`                 |
| `ECR_BACKEND_REPOSITORY_URL`     | `ecr_backend_repository_url`     |
| `ECR_FRONTEND_REPOSITORY_URL`    | `ecr_frontend_repository_url`    |
| `APP_URL`                        | `app_url`                        |

Requires `gh auth login` once. The deploy workflow
(`.github/workflows/deploy.yml`) then reads these secrets directly, so the
Redis/RDS hostnames and EC2 IP used at deploy time always match what
Terraform actually created - no more doketela/dokotela typos.

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

Run this after a deploy/debugging session to avoid paying for idle
infrastructure. Since `terraform.tfstate` stays on your machine, keep it
somewhere safe (it's gitignored) - if you lose it, `terraform apply` again
from a clean state will try to recreate everything from scratch.
