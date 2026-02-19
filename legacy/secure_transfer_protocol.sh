#!/bin/bash
#
# Portfolio/Educational Purpose Only
# -----------------------------------------------------------------------------
# Script: secure_transfer_protocol.sh
# Description: Orchestrates the secure transfer of the final data package to
#              the researcher's staging area. Uses rsync with strict permissions
#              and verification.
#

# --- Configuration ---
SOURCE_DIR="./data/delivery"
DEST_ROOT="./data/researcher_staging"
PROJECT_ID="NBR030"
DEST_DIR="${DEST_ROOT}/${PROJECT_ID}_Delivery_$(date +'%Y%m%d')"

echo "=== Secure Data Transfer Protocol ==="
echo "Source: ${SOURCE_DIR}"
echo "Destination: ${DEST_DIR}"

# --- Step 1: Pre-transfer Checks ---
echo "Step 1: Verifying permissions..."
mkdir -p "${DEST_ROOT}"
if [ ! -w "${DEST_ROOT}" ]; then
    echo "ERROR: No write permission to destination root."
    exit 1
fi

# --- Step 2: Execution ---
echo "Step 2: Executing transfer..."
mkdir -p "${DEST_DIR}"

# Rsync flags:
# -a: Archive mode (preserve permissions, times, etc.)
# --info=progress2: Show overall progress bar
# --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r: Set standard permissions
rsync -a --info=progress2 \
      --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
      "${SOURCE_DIR}/" "${DEST_DIR}/"

# --- Step 3: Verification ---
echo "Step 3: Verifying transfer..."
SRC_COUNT=$(ls -1 "${SOURCE_DIR}" | wc -l)
DEST_COUNT=$(ls -1 "${DEST_DIR}" | wc -l)

if [ "${SRC_COUNT}" -eq "${DEST_COUNT}" ]; then
    echo "SUCCESS: File counts match (${DEST_COUNT} files)."
    ls -lh "${DEST_DIR}"
else
    echo "WARNING: File count mismatch!"
fi

echo "=== Transfer Complete ==="
