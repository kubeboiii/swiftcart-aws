#!/usr/bin/env bash
# Format and mount the dedicated gp3 EBS volume on the Inventory EC2 (VPC B).
# The volume is attached as /dev/sdf and appears to the kernel as /dev/xvdf.
set -euo pipefail

DEVICE="/dev/xvdf"
MOUNT_POINT="/mnt/inventory_cache"

# 1. Verify the kernel sees the new raw block device (xvdf, no partitions)
lsblk

# 2. Format with XFS (optimized for high-throughput database workloads)
sudo mkfs -t xfs "${DEVICE}"

# 3. Create the mount point
sudo mkdir -p "${MOUNT_POINT}"

# 4. Mount the volume
sudo mount "${DEVICE}" "${MOUNT_POINT}"

# 5. Verify
df -h "${MOUNT_POINT}"

# 6. Make it persistent via UUID (safer than device names which can shift)
sudo blkid "${DEVICE}"
echo "# Replace YOUR-UUID with the UUID printed by blkid above:"
echo 'echo "UUID=YOUR-UUID /mnt/inventory_cache xfs defaults,nofail 0 2" | sudo tee -a /etc/fstab'
