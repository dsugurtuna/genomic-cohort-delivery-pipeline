#!/bin/bash
#
# Portfolio/Educational Purpose Only
# -----------------------------------------------------------------------------
# This script is part of a bioinformatics portfolio demonstrating technical
# competencies in genomic data engineering and secure data delivery.
#
# It contains sanitized code derived from production workflows. All internal
# paths, keys, and proprietary data have been removed or replaced with
# generic placeholders.
#
# Disclaimer: This code is for demonstration purposes and is not intended
# for clinical use without validation.
# -----------------------------------------------------------------------------
#
# Script: filter_cohort_samples.sh
# Description: Performs rigorous sample filtering based on exclusion criteria
#              (e.g., gender mismatches, withdrawals). Uses efficient AWK
#              processing to handle large ID lists reliably.
#

# --- Configuration ---
SAMPLES_TO_DROP="./data/metadata/exclusion_list_gender_mismatch.csv"
ORIGINAL_KEEP_LIST="./data/metadata/cohort_all_samples.txt"
FILTERED_KEEP_LIST="./data/processed/cohort_filtered_samples.txt"

echo "=== Cohort Filtering Pipeline ==="
echo "Exclusion List: ${SAMPLES_TO_DROP}"
echo "Original Cohort: ${ORIGINAL_KEEP_LIST}"
echo "Output List: ${FILTERED_KEEP_LIST}"
echo "---------------------------------"

# Simulation: Create dummy inputs if missing
mkdir -p "$(dirname "${SAMPLES_TO_DROP}")" "$(dirname "${FILTERED_KEEP_LIST}")"
if [ ! -f "${SAMPLES_TO_DROP}" ]; then
    echo "SampleID,Reason" > "${SAMPLES_TO_DROP}"
    echo "SAMP_001,GenderMismatch" >> "${SAMPLES_TO_DROP}"
    echo "SAMP_002,Withdrawal" >> "${SAMPLES_TO_DROP}"
fi
if [ ! -f "${ORIGINAL_KEEP_LIST}" ]; then
    echo "SAMP_001" > "${ORIGINAL_KEEP_LIST}"
    echo "SAMP_002" >> "${ORIGINAL_KEEP_LIST}"
    echo "SAMP_003" >> "${ORIGINAL_KEEP_LIST}"
    echo "SAMP_004" >> "${ORIGINAL_KEEP_LIST}"
fi

# --- Step 1: Extract IDs to Remove ---
echo "Step 1: Parsing exclusion list..."
# Extract first column (ID), remove carriage returns
awk -F, 'NR>1 {print $1}' "${SAMPLES_TO_DROP}" | tr -d '\r' > samples_to_remove.tmp

REMOVE_COUNT=$(wc -l < samples_to_remove.tmp)
echo "Identified ${REMOVE_COUNT} samples for removal."

# --- Step 2: Filter the Cohort ---
echo "Step 2: Applying filter..."
# AWK Logic:
# 1. Read removal list into array 'a' (NR==FNR)
# 2. For the second file (original list), print line only if ID ($2 or $1) is NOT in 'a'
# Note: Assuming single column ID list for simplicity here
awk 'NR==FNR{a[$1];next} !($1 in a)' samples_to_remove.tmp "${ORIGINAL_KEEP_LIST}" > "${FILTERED_KEEP_LIST}"

# --- Step 3: Verification ---
ORIG_COUNT=$(wc -l < "${ORIGINAL_KEEP_LIST}")
FINAL_COUNT=$(wc -l < "${FILTERED_KEEP_LIST}")
EXPECTED=$((ORIG_COUNT - REMOVE_COUNT))

echo "Step 3: Verification Results"
echo "  Original Count: ${ORIG_COUNT}"
echo "  Removed Count:  ${REMOVE_COUNT}"
echo "  Final Count:    ${FINAL_COUNT}"

if [ "${FINAL_COUNT}" -eq "${EXPECTED}" ]; then
    echo "SUCCESS: Sample counts match expectations."
else
    echo "WARNING: Discrepancy detected. Expected ${EXPECTED}, got ${FINAL_COUNT}."
fi

# Cleanup
rm samples_to_remove.tmp
echo "=== Filtering Complete ==="
