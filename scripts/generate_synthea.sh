#!/usr/bin/env bash
# Generate synthetic FHIR R4 patients with Synthea (mechanical/integration data only).
# Usage:
#   ./scripts/generate_synthea.sh            # default: 10 patients
#   ./scripts/generate_synthea.sh 50         # custom population
#   POPULATION=5 AGE=70 ./scripts/generate_synthea.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="${ROOT}/.tools"
SYNTHEA_DIR="${TOOLS_DIR}/synthea"
OUT_DIR="${ROOT}/data/synthea"
POPULATION="${1:-${POPULATION:-10}}"
# ICU-flavored default: older adults (higher acuity proxy for solo sim)
AGE="${AGE:-65}"
SEED="${SEED:-42}"
SYNTHEA_VERSION="${SYNTHEA_VERSION:-master}"

mkdir -p "${TOOLS_DIR}" "${OUT_DIR}"

if [[ ! -d "${SYNTHEA_DIR}/.git" ]]; then
  echo "Cloning Synthea into ${SYNTHEA_DIR}..."
  git clone --depth 1 --branch "${SYNTHEA_VERSION}" \
    https://github.com/synthetichealth/synthea.git "${SYNTHEA_DIR}"
fi

echo "Generating ${POPULATION} Synthea patients (seed=${SEED}, age≈${AGE}+) → ${OUT_DIR}"
cd "${SYNTHEA_DIR}"

# Prefer Gradle wrapper; Synthea writes FHIR to output/fhir by default
./gradlew run \
  -Psynthea.args="-p ${POPULATION} -s ${SEED} --exporter.fhir.export=true --exporter.csv.export=false --exporter.ccda.export=false --generate.only_alive_patients=true --generate.age_range_start=${AGE}" \
  || ./run_synthea -p "${POPULATION}" -s "${SEED}" \
    --exporter.fhir.export=true \
    --exporter.csv.export=false \
    --exporter.ccda.export=false

# Copy FHIR bundles into repo data dir (leave Synthea output intact for re-runs)
rm -rf "${OUT_DIR}/fhir"
mkdir -p "${OUT_DIR}/fhir"
if [[ -d "${SYNTHEA_DIR}/output/fhir" ]]; then
  cp -R "${SYNTHEA_DIR}/output/fhir/." "${OUT_DIR}/fhir/"
else
  echo "ERROR: expected ${SYNTHEA_DIR}/output/fhir after generation" >&2
  exit 1
fi

COUNT="$(find "${OUT_DIR}/fhir" -type f -name '*.json' | wc -l | tr -d ' ')"
echo "Done. ${COUNT} FHIR JSON files in ${OUT_DIR}/fhir"
echo "NOTE: Synthea output is for pipeline/integration testing only — not clinical validation."
