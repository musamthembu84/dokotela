#!/usr/bin/env bash
#
# Reads real infrastructure values straight out of Terraform state and pushes
# them into GitHub Actions repository secrets, so nobody ever has to
# hand-type an EC2 IP or a Redis/RDS endpoint into GitHub again (this is
# exactly what caused the doketela/dokotela Redis DNS mismatch).
#
# Usage (run from the terraform/ directory, after `terraform apply`):
#   ./sync-outputs-to-github-secrets.sh
#
# Requirements:
#   - GitHub CLI (`gh`) installed and authenticated: gh auth login
#   - Run from within the git repo (or set GH_REPO=owner/repo)
#
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: GitHub CLI ('gh') is required. Install it from https://cli.github.com/ and run 'gh auth login'." >&2
  exit 1
fi

if ! command -v terraform >/dev/null 2>&1; then
  echo "ERROR: terraform is required on PATH." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "Reading Terraform outputs"
echo "========================================="

EC2_PUBLIC_IP="$(terraform output -raw ec2_public_ip)"
RDS_ENDPOINT="$(terraform output -raw rds_endpoint)"
REDIS_ENDPOINT="$(terraform output -raw redis_endpoint)"
ECR_BACKEND_REPOSITORY_URL="$(terraform output -raw ecr_backend_repository_url)"
ECR_FRONTEND_REPOSITORY_URL="$(terraform output -raw ecr_frontend_repository_url)"
APP_URL="$(terraform output -raw app_url)"

echo "EC2 public IP:            $EC2_PUBLIC_IP"
echo "RDS endpoint:              $RDS_ENDPOINT"
echo "Redis endpoint:            $REDIS_ENDPOINT"
echo "ECR backend repository:    $ECR_BACKEND_REPOSITORY_URL"
echo "ECR frontend repository:   $ECR_FRONTEND_REPOSITORY_URL"
echo "App URL:                   $APP_URL"

echo "========================================="
echo "Pushing values into GitHub Actions secrets"
echo "========================================="

gh secret set EC2_PUBLIC_IP --body "$EC2_PUBLIC_IP"
gh secret set AWS_RDS_ENDPOINT --body "$RDS_ENDPOINT"
gh secret set AWS_REDIS_ENDPOINT --body "$REDIS_ENDPOINT"
gh secret set ECR_BACKEND_REPOSITORY_URL --body "$ECR_BACKEND_REPOSITORY_URL"
gh secret set ECR_FRONTEND_REPOSITORY_URL --body "$ECR_FRONTEND_REPOSITORY_URL"
gh secret set APP_URL --body "$APP_URL"

echo "========================================="
echo "Done. GitHub secrets now match Terraform outputs exactly."
echo "========================================="
