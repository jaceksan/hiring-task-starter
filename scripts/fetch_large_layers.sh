#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/data/large"

mkdir -p "${OUT_DIR}/geofabrik" "${OUT_DIR}/ghsl"

echo "Downloading Geofabrik Czech Republic extracts..."
curl -L --fail -sS --retry 3 --retry-delay 2 --retry-connrefused -C - \
  'https://download.geofabrik.de/europe/czech-republic-latest.osm.pbf' \
  -o "${OUT_DIR}/geofabrik/czech-republic-latest.osm.pbf"
curl -L --fail -sS --retry 3 --retry-delay 2 --retry-connrefused -C - \
  'https://download.geofabrik.de/europe/czech-republic-latest.osm.pbf.md5' \
  -o "${OUT_DIR}/geofabrik/czech-republic-latest.osm.pbf.md5"

curl -L --fail -sS --retry 3 --retry-delay 2 --retry-connrefused -C - \
  'https://download.geofabrik.de/europe/czech-republic-latest-free.shp.zip' \
  -o "${OUT_DIR}/geofabrik/czech-republic-latest-free.shp.zip"
curl -L --fail -sS --retry 3 --retry-delay 2 --retry-connrefused -C - \
  'https://download.geofabrik.de/europe/czech-republic-latest-free.shp.zip.md5' \
  -o "${OUT_DIR}/geofabrik/czech-republic-latest-free.shp.zip.md5"

echo "Downloading GHSL global population grid (E2025, 30 arcsec)..."
curl -L --fail -sS --retry 3 --retry-delay 2 --retry-connrefused -C - \
  'https://cidportal.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/GHS_POP_E2025_GLOBE_R2023A_4326_30ss/V1-0/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip' \
  -o "${OUT_DIR}/ghsl/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip"

echo
echo "Done. Tip: this folder is git-ignored (data/large/)."

