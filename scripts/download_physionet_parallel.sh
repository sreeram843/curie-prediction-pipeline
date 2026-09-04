#!/usr/bin/env bash
# Download the credentialed PhysioNet datasets concurrently.
#
# Usage:
#   PHYSIONET_USERNAME=sreeram43 ./scripts/download_physionet_parallel.sh
#
# The single-dataset downloader asks for the password once per dataset. Output is
# displayed and copied to a separate log for each dataset. At most four dataset
# jobs are started; do not add file-level parallelism without checking PhysioNet's
# access policy and the resulting server load.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOWNLOADER="${ROOT}/scripts/download_physionet_credentialed.sh"
LOG_ROOT="${PHYSIONET_LOG_ROOT:-/Users/srirammentey/PhysioNet/logs}"

if [[ -z "${PHYSIONET_USERNAME:-}" ]]; then
  echo "ERROR: set PHYSIONET_USERNAME before running this script." >&2
  exit 1
fi

if [[ ! -x "${DOWNLOADER}" ]]; then
  echo "ERROR: downloader is not executable: ${DOWNLOADER}" >&2
  echo "Run: chmod 700 ${DOWNLOADER}" >&2
  exit 1
fi

mkdir -p "${LOG_ROOT}"
chmod 700 "${LOG_ROOT}"

DATASETS=(mimiciv note fhir eicu ed)
PIDS=()
NAMES=()

for dataset in "${DATASETS[@]}"; do
  log_file="${LOG_ROOT}/${dataset}.log"

  echo "Starting ${dataset}; log: ${log_file}"
  (
    set -o pipefail
    "${DOWNLOADER}" "${dataset}" 2>&1 | tee "${log_file}"
  ) &

  PIDS+=("$!")
  NAMES+=("${dataset}")
done

failed=0

for index in "${!PIDS[@]}"; do
  if wait "${PIDS[$index]}"; then
    echo "${NAMES[${index}]} completed successfully"
  else
    echo "${NAMES[${index}]} failed; inspect ${LOG_ROOT}/${NAMES[${index}]}.log" >&2
    failed=1
  fi
done

exit "${failed}"
