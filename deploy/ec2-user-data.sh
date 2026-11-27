#!/bin/bash
# Get Well OCR: EC2 boot script (paste into "User data" when launching the instance).
#
# Requirements:
#   - Amazon Linux 2023, x86 (t3.medium), region eu-north-1
#   - IAM instance profile with AmazonEC2ContainerRegistryReadOnly
#     (+ ssm:GetParameter on /gwo/* if you store Azure secrets in Parameter Store)
#
# What it does: installs Docker, installs a systemd service "gwo" that logs in to ECR,
# pulls the image and runs the API on port 8000. The service starts on every boot.
#
# Later:
#   new version:   sudo sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=v2/' /etc/gwo/gwo.conf && sudo systemctl restart gwo
#   logs:          sudo journalctl -u gwo -f      (boot script itself: /var/log/gwo-user-data.log)
#
# Optional Azure secrets (SecureString in SSM Parameter Store, same region):
#   /gwo/AZURE_DI_ENDPOINT   /gwo/AZURE_DI_KEY   /gwo/OCR_ENGINE
set -euo pipefail
exec > >(tee -a /var/log/gwo-user-data.log) 2>&1

# ---------- settings ----------
mkdir -p /etc/gwo
cat > /etc/gwo/gwo.conf <<'EOF'
AWS_REGION=eu-north-1
REGISTRY=363183905530.dkr.ecr.eu-north-1.amazonaws.com
IMAGE_NAME=get-well-ocr
IMAGE_TAG=v1
HOST_PORT=8000
EOF

# ---------- Docker ----------
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user

# ---------- start script (runs on every service start) ----------
cat > /usr/local/bin/gwo-start <<'EOF'
#!/bin/bash
set -euo pipefail
source /etc/gwo/gwo.conf
IMAGE="$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

# Secrets from Parameter Store (if present) -> env file only root can read
param() { aws ssm get-parameter --region "$AWS_REGION" --name "/gwo/$1" --with-decryption \
            --query Parameter.Value --output text 2>/dev/null || true; }
umask 077
{
  echo "OCR_ENGINE=$(param OCR_ENGINE | grep . || echo tesseract)"
  v=$(param AZURE_DI_ENDPOINT); [ -n "$v" ] && echo "AZURE_DI_ENDPOINT=$v"
  v=$(param AZURE_DI_KEY);      [ -n "$v" ] && echo "AZURE_DI_KEY=$v"
  true
} > /etc/gwo/env

# Pull the image (retry: network/IAM may need a moment right after boot)
for i in 1 2 3 4 5; do
  aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "$REGISTRY" && docker pull "$IMAGE" && break
  echo "pull failed, retry $i/5"; sleep 10
done

docker rm -f gwo-api 2>/dev/null || true
exec docker run --name gwo-api --rm \
  -p "$HOST_PORT":8000 --env-file /etc/gwo/env \
  -v gwo-private:/app/data/private -v gwo-outputs:/app/outputs -v gwo-cache:/app/cache \
  "$IMAGE"
EOF
chmod 755 /usr/local/bin/gwo-start

# ---------- systemd service ----------
cat > /etc/systemd/system/gwo.service <<'EOF'
[Unit]
Description=Get Well OCR API (Docker)
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
ExecStart=/usr/local/bin/gwo-start
ExecStop=/usr/bin/docker stop gwo-api
Restart=always
RestartSec=10
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now gwo
echo "gwo service started: $(date)"
