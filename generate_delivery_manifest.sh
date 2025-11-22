#!/bin/bash
#
# Portfolio/Educational Purpose Only
# -----------------------------------------------------------------------------
# Script: generate_delivery_manifest.sh
# Description: Generates a comprehensive checksum manifest and status report
#              for the data delivery. Ensures traceability and data integrity
#              during transfer.
#

# --- Configuration ---
DELIVERY_DIR="./data/delivery"
PROJECT_ID="NBR030"
MANIFEST_FILE="${DELIVERY_DIR}/MANIFEST.tsv"
STATUS_FILE="${DELIVERY_DIR}/STATUS_SUMMARY.tsv"

echo "=== Generating Delivery Manifest ==="

# Simulation: Ensure delivery dir exists
mkdir -p "${DELIVERY_DIR}"
if [ -z "$(ls -A ${DELIVERY_DIR})" ]; then
    touch "${DELIVERY_DIR}/${PROJECT_ID}_final_genotypes.vcf.gz"
    touch "${DELIVERY_DIR}/${PROJECT_ID}_sample_linkage.txt"
fi

# --- Step 1: Checksum Generation ---
echo "Step 1: Calculating checksums (MD5/SHA1)..."
echo -e "Filename\tMD5\tSHA1" > "${MANIFEST_FILE}"

for file in "${DELIVERY_DIR}"/*; do
    if [ -f "$file" ] && [[ "$file" != *MANIFEST.tsv ]] && [[ "$file" != *STATUS_SUMMARY.tsv ]]; then
        filename=$(basename "$file")
        # Simulation: Generate fake hashes
        md5="d41d8cd98f00b204e9800998ecf8427e" 
        sha1="da39a3ee5e6b4b0d3255bfef95601890afd80709"
        
        # Real command:
        # md5=$(md5sum "$file" | awk '{print $1}')
        # sha1=$(sha1sum "$file" | awk '{print $1}')
        
        echo -e "${filename}\t${md5}\t${sha1}" >> "${MANIFEST_FILE}"
    fi
done
echo "Manifest saved to ${MANIFEST_FILE}"

# --- Step 2: Status Summary ---
echo "Step 2: Generating status report..."
VCF_FILE="${DELIVERY_DIR}/${PROJECT_ID}_final_genotypes.vcf.gz"
LINKAGE_FILE="${DELIVERY_DIR}/${PROJECT_ID}_sample_linkage.txt"

# Simulation: Mock counts
VCF_SAMPLES=10732
LINKAGE_ROWS=10732

{
  echo -e "Metric\tValue"
  echo -e "Project_ID\t${PROJECT_ID}"
  echo -e "Delivery_Date\t$(date +'%Y-%m-%d')"
  echo -e "VCF_Sample_Count\t${VCF_SAMPLES}"
  echo -e "Linkage_Row_Count\t${LINKAGE_ROWS}"
  echo -e "Integrity_Check\tPASS"
} > "${STATUS_FILE}"

echo "Status summary saved to ${STATUS_FILE}"
echo "=== Manifest Generation Complete ==="
