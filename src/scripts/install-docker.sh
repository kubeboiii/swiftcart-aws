#!/usr/bin/env bash
# Install Docker + Docker Compose on the Web Portal EC2 host (Amazon Linux 2).
# Log out and back in afterward so the docker group membership takes effect.
set -euo pipefail

sudo yum update -y
sudo amazon-linux-extras install docker -y
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# Download docker-compose
sudo curl -L \
  "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

echo "Done. Log out and back in, then: docker-compose up -d --build"
