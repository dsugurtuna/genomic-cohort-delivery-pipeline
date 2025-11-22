# Genomic Cohort Delivery Pipeline

**An industrial-grade pipeline for the assembly, correction, and secure delivery of large-scale genomic cohorts.**

This repository showcases a complete "Data Engineering for Biobanking" workflow. It addresses the complex challenge of assembling a clean, multi-batch cohort from raw genotype data, resolving technical conflicts (SNP mismatches), and packaging the result for clinical research.

## 📂 Repository Contents

| Script | Role | Description |
| :--- | :--- | :--- |
| `filter_cohort_samples.sh` | **Cohort Definition** | Rigorously filters participant lists based on exclusion criteria (e.g., gender mismatches, withdrawals) using high-performance AWK processing. |
| `merge_and_correct_genotypes.sh` | **Core Engine** | The "Heavy Lifter". Automates the extraction of samples from multiple batches, detects merge conflicts (flip errors), auto-corrects them, and produces a final clean VCF. |
| `generate_delivery_manifest.sh` | **Quality Assurance** | Generates cryptographic checksums (MD5/SHA1) and status reports to ensure data integrity and traceability. |
| `secure_transfer_protocol.sh` | **Deployment** | Orchestrates the secure, permission-controlled transfer of sensitive data to researcher staging areas. |

## 🌟 Key Capabilities

### 1. Automated Conflict Resolution
Merging genomic data from different batches often fails due to strand issues (flip errors).
*   **The Problem:** PLINK fails if SNP A is 'A/T' in Batch 1 but 'T/A' in Batch 2.
*   **My Solution:** The `merge_and_correct_genotypes.sh` script implements a **Self-Healing Workflow**:
    1.  Attempts a merge.
    2.  Catches the failure.
    3.  Parses the `.missnp` log to identify conflicting variants.
    4.  Re-extracts the data *excluding* those specific variants.
    5.  Successfully re-merges the cleaned data.

### 2. Rigorous Data Governance
*   **Exclusion Logic:** `filter_cohort_samples.sh` ensures that withdrawn participants are *never* included in a release, adhering to strict GDPR and bioethics standards.
*   **Manifest Generation:** Every delivery includes a machine-readable manifest, ensuring that what was sent is exactly what was received.

### 3. Operational Robustness
*   **Idempotency:** Scripts are designed to clean up after themselves and can be re-run safely.
*   **Traceability:** Detailed logging at every step (Extraction -> Merge -> Correction -> Conversion).

## 🛠️ Technical Stack

*   **PLINK 1.9/2.0**: For high-speed genotype manipulation.
*   **Bash/Shell**: For pipeline orchestration.
*   **AWK**: For complex text processing and ID filtering.
*   **Rsync**: For secure data transport.

---
*Created by [dsugurtuna](https://github.com/dsugurtuna)*
