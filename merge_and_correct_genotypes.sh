#!/bin/bash
#
# Portfolio/Educational Purpose Only
# -----------------------------------------------------------------------------
# Script: merge_and_correct_genotypes.sh
# Description: The core engine for assembling a multi-batch cohort.
#              1. Extracts samples from multiple source batches.
#              2. Attempts a merge.
#              3. Automatically detects and removes mismatched SNPs (flip errors).
#              4. Re-merges and converts to VCF.
#

# Stop on error
set -e

# --- Configuration ---
SOURCE_DATA_DIR="./data/raw_batches"
FILTERED_KEEP_LIST="./data/processed/cohort_filtered_samples.txt"
WORK_DIR="./data/work"
FINAL_PREFIX="Cohort_Final_Genotypes"
PLINK_EXEC="plink" # Assumes plink is in PATH

echo "=== Genotype Assembly & Correction Pipeline ==="

# Simulation Setup
mkdir -p "${WORK_DIR}"
mkdir -p "${SOURCE_DATA_DIR}"
# Create dummy batch files for simulation if they don't exist
if [ -z "$(ls -A ${SOURCE_DATA_DIR})" ]; then
    touch "${SOURCE_DATA_DIR}/batch_01.bed" "${SOURCE_DATA_DIR}/batch_01.bim" "${SOURCE_DATA_DIR}/batch_01.fam"
    touch "${SOURCE_DATA_DIR}/batch_02.bed" "${SOURCE_DATA_DIR}/batch_02.bim" "${SOURCE_DATA_DIR}/batch_02.fam"
fi

# --- Step 1: Initial Extraction ---
echo "Step 1: Extracting cohort samples from source batches..."
find "${SOURCE_DATA_DIR}" -name "*.bed" | sed 's/\.bed//' > "${WORK_DIR}/bfile_list.txt"

# Mocking PLINK execution loop
while read bfile; do
    batch_name=$(basename "${bfile}")
    echo "  Processing ${batch_name}..."
    # Real command:
    # $PLINK_EXEC --bfile "${bfile}" --keep "${FILTERED_KEEP_LIST}" --make-bed --out "${WORK_DIR}/${batch_name}_subset"
    
    # Simulation:
    touch "${WORK_DIR}/${batch_name}_subset.bed"
done < "${WORK_DIR}/bfile_list.txt"

# --- Step 2: First Merge Attempt (Detect Conflicts) ---
echo "Step 2: Attempting initial merge..."
find "${WORK_DIR}" -name "*_subset.bed" | sed 's/\.bed//' > "${WORK_DIR}/merge_list.txt"

# Real command:
# $PLINK_EXEC --merge-list "${WORK_DIR}/merge_list.txt" --make-bed --out "${WORK_DIR}/merge_attempt" || true

# Simulation: Create a fake .missnp file to simulate a merge conflict
echo "rs12345" > "${WORK_DIR}/merge_attempt-merge.missnp"
echo "  [Simulation] Merge conflict detected (simulated)."

# --- Step 3: Conflict Resolution ---
echo "Step 3: Resolving SNP conflicts..."
MISSNP_FILE="${WORK_DIR}/merge_attempt-merge.missnp"

if [ -f "${MISSNP_FILE}" ]; then
    echo "  Excluding $(wc -l < "${MISSNP_FILE}") problematic SNPs..."
    
    while read bfile; do
        batch_name=$(basename "${bfile}")
        # Real command:
        # $PLINK_EXEC --bfile "${bfile}" --keep "${FILTERED_KEEP_LIST}" --exclude "${MISSNP_FILE}" --make-bed --out "${WORK_DIR}/${batch_name}_corrected"
        
        # Simulation:
        touch "${WORK_DIR}/${batch_name}_corrected.bed"
    done < "${WORK_DIR}/bfile_list.txt"
else
    echo "  No conflicts found. Proceeding with original subsets."
fi

# --- Step 4: Final Merge ---
echo "Step 4: Performing final merge..."
find "${WORK_DIR}" -name "*_corrected.bed" | sed 's/\.bed//' > "${WORK_DIR}/merge_list_final.txt"

# Real command:
# $PLINK_EXEC --merge-list "${WORK_DIR}/merge_list_final.txt" --make-bed --out "${WORK_DIR}/${FINAL_PREFIX}"

# Simulation:
touch "${WORK_DIR}/${FINAL_PREFIX}.bed" "${WORK_DIR}/${FINAL_PREFIX}.bim" "${WORK_DIR}/${FINAL_PREFIX}.fam"
echo "  Merge successful."

# --- Step 5: VCF Conversion ---
echo "Step 5: Converting to VCF..."
# Real command:
# $PLINK_EXEC --bfile "${WORK_DIR}/${FINAL_PREFIX}" --recode vcf bgz --out "${WORK_DIR}/${FINAL_PREFIX}"

# Simulation:
touch "${WORK_DIR}/${FINAL_PREFIX}.vcf.gz"

echo "=== Pipeline Complete ==="
echo "Final Output: ${WORK_DIR}/${FINAL_PREFIX}.vcf.gz"
