#!/usr/bin/env bash
set -euo pipefail

ECR_REPOSITORY_URL=$(
  terraform -chdir=terraform output -raw ecr_repository_url
)

IMAGE_TAG=$(git rev-parse HEAD)

IMAGE="$ECR_REPOSITORY_URL:$IMAGE_TAG"

echo "Deploying image:"
echo "$IMAGE"

sed "s|IMAGE_PLACEHOLDER|$IMAGE|g" \
  k8s/deployment.yaml \
  | kubectl apply -f -

kubectl apply -f k8s/service.yaml

kubectl rollout status deployment/fastapi