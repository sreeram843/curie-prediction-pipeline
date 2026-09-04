#!/usr/bin/env bash
# Download one credentialed PhysioNet dataset outside the repository.
#
# Usage:
#   PHYSIONET_USERNAME=sreeram43 ./scripts/download_physionet_credentialed.sh mimiciv
#   PHYSIONET_USERNAME=sreeram43 ./scripts/download_physionet_credentialed.sh note
#   PHYSIONET_USERNAME=sreeram43 ./scripts/download_physionet_credentialed.sh fhir
#   PHYSIONET_USERNAME=sreeram43 ./scripts/download_physionet_credentialed.sh eicu
#   PHYSIONET_USERNAME=sreeram43 ./scripts/download_physionet_credentialed.sh ed
#
# The PhysioNet password is requested interactively and is never written by this script.
# Downloads resume with wget -c and compressed files are checked with gzip -t.

set -Eeuo pipefail

DATA_ROOT="${PHYSIONET_DATA_ROOT:-/Users/srirammentey/PhysioNet}"
USERNAME="${PHYSIONET_USERNAME:-}"

if [[ -z "${USERNAME}" ]]; then
  echo "ERROR: set PHYSIONET_USERNAME before running this script." >&2
  exit 1
fi

if ! command -v wget >/dev/null 2>&1; then
  echo "ERROR: wget is required." >&2
  exit 1
fi

if ! command -v gzip >/dev/null 2>&1; then
  echo "ERROR: gzip is required." >&2
  exit 1
fi

download_dataset() {
  local name="$1"
  local url="$2"
  local target="${DATA_ROOT}/${name}"

  mkdir -p "${target}"
  chmod 700 "${DATA_ROOT}" "${target}"

  echo
  echo "Downloading ${name}"
  echo "Destination: ${target}"
  echo "Enter your PhysioNet password when prompted."

  (
    cd "${target}"
    wget -r -N -c -np \
      --user "${USERNAME}" \
      --ask-password \
      --show-progress \
      --tries=3 \
      --timeout=60 \
      --waitretry=10 \
      "${url}"
  )

  echo "Validating compressed files for ${name}..."
  while IFS= read -r -d '' file; do
    gzip -t "${file}"
  done < <(find "${target}" -type f -name '*.gz' -print0)

  echo "Completed and validated: ${name}"
  du -sh "${target}"
}

case "${1:-}" in
  mimiciv)
    download_dataset \
      "mimiciv-v3.1" \
      "https://physionet.org/files/mimiciv/3.1/"
    ;;
  note)
    download_dataset \
      "mimic-iv-note-v2.2" \
      "https://physionet.org/files/mimic-iv-note/2.2/"
    ;;
  fhir)
    download_dataset \
      "mimic-iv-fhir-v2.1" \
      "https://physionet.org/files/mimic-iv-fhir/2.1/"
    ;;
  eicu)
    download_dataset \
      "eicu-crd-v2.0" \
      "https://physionet.org/files/eicu-crd/2.0/"
    ;;
  ed)
    download_dataset \
      "mimic-iv-ed-v2.2" \
      "https://physionet.org/files/mimic-iv-ed/2.2/"
    ;;
  *)
    echo "Usage: $0 {mimiciv|note|fhir|eicu|ed}" >&2
    exit 2
    ;;
esac
