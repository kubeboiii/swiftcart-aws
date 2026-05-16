#!/usr/bin/env bash
# Mount the shared EFS file system on a Web Portal EC2 instance (VPC A).
# Replace fs-YOUR_EFS_ID with the real EFS ID from the console.
set -euo pipefail

EFS_ID="fs-YOUR_EFS_ID"
MOUNT_POINT="/var/www/swiftcart/shared_uploads"

# 1. Install the Amazon EFS utilities
sudo yum install -y amazon-efs-utils

# 2. Create the mount point directory
sudo mkdir -p "${MOUNT_POINT}"

# 3. Mount the EFS file system (TLS in transit)
sudo mount -t efs -o tls "${EFS_ID}:/" "${MOUNT_POINT}"

# 4. Verify the mount
df -hT | grep efs

# 5. Make it persistent across reboots
sudo cp /etc/fstab /etc/fstab.bak
echo "${EFS_ID}:/ ${MOUNT_POINT} efs _netdev,tls 0 0" | sudo tee -a /etc/fstab
