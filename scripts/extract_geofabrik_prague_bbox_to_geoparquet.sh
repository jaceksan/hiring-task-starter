#!/usr/bin/env bash
set -euo pipefail

#
# Extract a demo-sized AOI slice from Geofabrik "free shapefile" bundle into GeoParquet.
#
# Why this script exists:
# - Avoid slow, row-by-row ingestion (no INSERT-many).
# - Use GDAL/ogr2ogr as the bulk converter (fast path).
# - Produce GeoParquet optimized for AOI slicing (covering bbox + optional spatial clustering).
#

usage() {
  cat <<'EOF'
Usage:
  ./scripts/extract_geofabrik_prague_bbox_to_geoparquet.sh [options]

Options:
  --zip PATH
      Path to Geofabrik "free shapefile" zip.
      Default: data/large/geofabrik/czech-republic-latest-free.shp.zip

  --shp-dir DIR
      Directory where the ZIP is (or will be) extracted.
      Default: data/large/geofabrik/cz-free-shp

  --aoi PRESET
      AOI preset. One of:
        prague_bbox  (default; minLon=14.22 minLat=49.94 maxLon=14.70 maxLat=50.18)
        cz_bbox      (whole-country-ish bbox; slower & bigger output)

  --bbox "minLon minLat maxLon maxLat"
      Override the bbox explicitly (space-separated).

  --scenario-id ID
      Output scenario folder name under data/derived/.
      Default: czech_population_infrastructure_large

  --out-dir DIR
      Override output directory (defaults under data/derived/{scenario-id}/{aoi}/).

  --compression CODEC
      Parquet compression codec. Default: SNAPPY

  --sort-by-bbox 0|1
      Enable GDAL Parquet SORT_BY_BBOX for better spatial locality.
      Default: 1

  --row-group-size N
      Parquet row group size. Default: 65536

  --list-top N
      When listing extracted files, show only first N lines (debugging).
      Default: 0 (disabled)

Notes:
  - This script expects an ogr2ogr build with Parquet support:
      ogrinfo --formats | grep -i parquet
  - Every executed command is prefixed with 'time' to show elapsed time.

EOF
}

step() {
  echo
  echo "==> $*"
}

run() {
  # Print the exact command for transparency.
  echo "+ $*"
  time "$@"
}

ZIP_PATH="data/large/geofabrik/czech-republic-latest-free.shp.zip"
SHP_DIR="data/large/geofabrik/cz-free-shp"
AOI_PRESET="prague_bbox"
BBOX=""
SCENARIO_ID="czech_population_infrastructure_large"
OUT_DIR=""
COMPRESSION="SNAPPY"
SORT_BY_BBOX="1"
ROW_GROUP_SIZE="65536"
LIST_TOP="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --zip)
      ZIP_PATH="${2:-}"; shift 2 ;;
    --shp-dir)
      SHP_DIR="${2:-}"; shift 2 ;;
    --aoi)
      AOI_PRESET="${2:-}"; shift 2 ;;
    --bbox)
      BBOX="${2:-}"; shift 2 ;;
    --scenario-id)
      SCENARIO_ID="${2:-}"; shift 2 ;;
    --out-dir)
      OUT_DIR="${2:-}"; shift 2 ;;
    --compression)
      COMPRESSION="${2:-}"; shift 2 ;;
    --sort-by-bbox)
      SORT_BY_BBOX="${2:-}"; shift 2 ;;
    --row-group-size)
      ROW_GROUP_SIZE="${2:-}"; shift 2 ;;
    --list-top)
      LIST_TOP="${2:-}"; shift 2 ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$BBOX" ]]; then
  case "$AOI_PRESET" in
    prague_bbox)
      BBOX="14.22 49.94 14.70 50.18"
      ;;
    cz_bbox)
      # Rough CZ bbox (WGS84). Big outputs; intended for stress testing only.
      BBOX="12.09 48.55 18.86 51.10"
      ;;
    *)
      echo "Unknown --aoi preset: $AOI_PRESET" >&2
      exit 2
      ;;
  esac
fi

if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="data/derived/${SCENARIO_ID}/${AOI_PRESET}"
fi

step "Config"
echo "ZIP_PATH=${ZIP_PATH}"
echo "SHP_DIR=${SHP_DIR}"
echo "AOI_PRESET=${AOI_PRESET}"
echo "BBOX=${BBOX}"
echo "SCENARIO_ID=${SCENARIO_ID}"
echo "OUT_DIR=${OUT_DIR}"
echo "COMPRESSION=${COMPRESSION}"
echo "SORT_BY_BBOX=${SORT_BY_BBOX}"
echo "ROW_GROUP_SIZE=${ROW_GROUP_SIZE}"
echo "LIST_TOP=${LIST_TOP}"

step "Check GDAL Parquet driver is available"
run bash -lc "ogrinfo --formats | grep -i parquet"

step "Create output directory"
run mkdir -p "$OUT_DIR"

step "Extract ZIP (if needed)"
if [[ ! -d "$SHP_DIR" ]] || [[ -z "$(ls -A "$SHP_DIR" 2>/dev/null || true)" ]]; then
  run mkdir -p "$SHP_DIR"
  run unzip -q "$ZIP_PATH" -d "$SHP_DIR"
else
  echo "+ (skip) already extracted: $SHP_DIR"
fi

step "Sanity-check expected source shapefiles exist"
echo "+ extracted file count:"
run bash -lc "ls -1 \"$SHP_DIR\" | wc -l"
if [[ "${LIST_TOP}" != "0" ]]; then
  echo "+ top ${LIST_TOP} entries:"
  run bash -lc "ls -1 \"$SHP_DIR\" | head -n \"$LIST_TOP\""
fi

ROADS_SHP="${SHP_DIR}/gis_osm_roads_free_1.shp"
WATER_A_SHP="${SHP_DIR}/gis_osm_water_a_free_1.shp"
PLACES_SHP="${SHP_DIR}/gis_osm_places_free_1.shp"

if [[ ! -f "$ROADS_SHP" ]]; then
  echo "Missing expected shapefile: $ROADS_SHP" >&2
  exit 1
fi
if [[ ! -f "$WATER_A_SHP" ]]; then
  echo "Missing expected shapefile: $WATER_A_SHP" >&2
  exit 1
fi
if [[ ! -f "$PLACES_SHP" ]]; then
  echo "Missing expected shapefile: $PLACES_SHP" >&2
  exit 1
fi

COMMON_LCO=(
  -lco "COMPRESSION=${COMPRESSION}"
  -lco "GEOMETRY_ENCODING=WKB"
  -lco "WRITE_COVERING_BBOX=YES"
  -lco "ROW_GROUP_SIZE=${ROW_GROUP_SIZE}"
)

if [[ "$SORT_BY_BBOX" == "1" ]]; then
  COMMON_LCO+=( -lco "SORT_BY_BBOX=YES" )
fi

step "Convert AOI-filtered roads (lines) -> GeoParquet"
run ogr2ogr -f Parquet "${OUT_DIR}/roads.parquet" "$ROADS_SHP" -spat $BBOX "${COMMON_LCO[@]}"

step "Convert AOI-filtered water areas (polygons) -> GeoParquet"
run ogr2ogr -f Parquet "${OUT_DIR}/water_areas.parquet" "$WATER_A_SHP" -spat $BBOX "${COMMON_LCO[@]}"

step "Convert AOI-filtered places (points) -> GeoParquet"
run ogr2ogr -f Parquet "${OUT_DIR}/places.parquet" "$PLACES_SHP" -spat $BBOX "${COMMON_LCO[@]}"

step "Verify outputs exist and look non-empty"
run bash -lc "for f in \"${OUT_DIR}/roads.parquet\" \"${OUT_DIR}/water_areas.parquet\" \"${OUT_DIR}/places.parquet\"; do if [[ -s \"\$f\" ]]; then echo \"OK: \$f\"; else echo \"MISSING/EMPTY: \$f\"; exit 1; fi; done"

step "Report number of created GeoParquet files"
echo "+ created file count:"
run bash -lc "ls -1 \"${OUT_DIR}\"/*.parquet 2>/dev/null | wc -l"

step "Quick DuckDB counts (non-empty check)"
run duckdb :memory: <<SQL
SELECT 'roads' AS layer, COUNT(*) AS n FROM read_parquet('${OUT_DIR}/roads.parquet')
UNION ALL
SELECT 'water_areas' AS layer, COUNT(*) AS n FROM read_parquet('${OUT_DIR}/water_areas.parquet')
UNION ALL
SELECT 'places' AS layer, COUNT(*) AS n FROM read_parquet('${OUT_DIR}/places.parquet');
SQL

step "Done"
