#!/usr/bin/env bash
set -euo pipefail

#
# Extract AOI slices from Geofabrik "free shapefile" bundle into GeoParquet.
#
# Why this script exists:
# - Avoid slow, row-by-row ingestion (no INSERT-many).
# - Use GDAL/ogr2ogr as the bulk converter (fast path).
# - Produce GeoParquet optimized for AOI slicing (covering bbox + optional spatial clustering).
# - Build a richer "places" layer by merging OSM settlements + POIs.
# - Build explicit flood-risk polygons from water areas for demo routing/rendering.
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
  - This script uses DuckDB Spatial (`ST_Read`) + `COPY ... TO parquet`.
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
POIS_SHP="${SHP_DIR}/gis_osm_pois_free_1.shp"

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
if [[ ! -f "$POIS_SHP" ]]; then
  echo "Missing expected shapefile: $POIS_SHP" >&2
  exit 1
fi

read -r MIN_LON MIN_LAT MAX_LON MAX_LAT <<<"$BBOX"

step "Convert AOI-filtered source shapefiles to raw GeoParquet via DuckDB Spatial"
run rm -f \
  "${OUT_DIR}/roads_raw.parquet" \
  "${OUT_DIR}/roads.parquet" \
  "${OUT_DIR}/water_areas_raw.parquet" \
  "${OUT_DIR}/places_raw.parquet" \
  "${OUT_DIR}/pois_raw.parquet" \
  "${OUT_DIR}/flood_zones.parquet" \
  "${OUT_DIR}/places.parquet"
run duckdb :memory: <<SQL
INSTALL spatial;
LOAD spatial;

COPY (
  SELECT
    osm_id,
    code,
    fclass,
    name,
    ref,
    oneway,
    maxspeed,
    layer,
    bridge,
    tunnel,
    CAST(geom AS GEOMETRY) AS geometry
  FROM ST_Read(
    '${ROADS_SHP}',
    spatial_filter_box := {min_x: ${MIN_LON}, min_y: ${MIN_LAT}, max_x: ${MAX_LON}, max_y: ${MAX_LAT}}
  )
) TO '${OUT_DIR}/roads_raw.parquet'
(FORMAT PARQUET, COMPRESSION '${COMPRESSION}', ROW_GROUP_SIZE ${ROW_GROUP_SIZE});

COPY (
  SELECT
    osm_id,
    code,
    fclass,
    name,
    CAST(geom AS GEOMETRY) AS geom
  FROM ST_Read(
    '${WATER_A_SHP}',
    spatial_filter_box := {min_x: ${MIN_LON}, min_y: ${MIN_LAT}, max_x: ${MAX_LON}, max_y: ${MAX_LAT}}
  )
) TO '${OUT_DIR}/water_areas_raw.parquet'
(FORMAT PARQUET, COMPRESSION '${COMPRESSION}', ROW_GROUP_SIZE ${ROW_GROUP_SIZE});

COPY (
  SELECT
    osm_id,
    code,
    fclass,
    population,
    name,
    CAST(geom AS GEOMETRY) AS geom
  FROM ST_Read(
    '${PLACES_SHP}',
    spatial_filter_box := {min_x: ${MIN_LON}, min_y: ${MIN_LAT}, max_x: ${MAX_LON}, max_y: ${MAX_LAT}}
  )
) TO '${OUT_DIR}/places_raw.parquet'
(FORMAT PARQUET, COMPRESSION '${COMPRESSION}', ROW_GROUP_SIZE ${ROW_GROUP_SIZE});

COPY (
  SELECT
    osm_id,
    code,
    fclass,
    name,
    CAST(geom AS GEOMETRY) AS geom
  FROM ST_Read(
    '${POIS_SHP}',
    spatial_filter_box := {min_x: ${MIN_LON}, min_y: ${MIN_LAT}, max_x: ${MAX_LON}, max_y: ${MAX_LAT}}
  )
) TO '${OUT_DIR}/pois_raw.parquet'
(FORMAT PARQUET, COMPRESSION '${COMPRESSION}', ROW_GROUP_SIZE ${ROW_GROUP_SIZE});
SQL

step "Build enriched flood_zones + places from raw extracts"
run duckdb :memory: <<SQL
INSTALL spatial;
LOAD spatial;

COPY (
SELECT
  osm_id,
  code,
  fclass,
  name,
  ref,
  oneway,
  maxspeed,
  layer,
  bridge,
  tunnel,
  CAST(geometry AS GEOMETRY) AS geometry,
  STRUCT_PACK(
    xmin := CAST(ST_XMin(geometry) AS FLOAT),
    ymin := CAST(ST_YMin(geometry) AS FLOAT),
    xmax := CAST(ST_XMax(geometry) AS FLOAT),
    ymax := CAST(ST_YMax(geometry) AS FLOAT)
  ) AS geometry_bbox
FROM read_parquet('${OUT_DIR}/roads_raw.parquet')
WHERE geometry IS NOT NULL
) TO '${OUT_DIR}/roads.parquet'
(FORMAT PARQUET, COMPRESSION '${COMPRESSION}');

COPY (
WITH water AS (
  SELECT
    CAST(osm_id AS VARCHAR) AS osm_id,
    CAST(code AS INTEGER) AS code,
    CAST(fclass AS VARCHAR) AS source_fclass,
    CAST(name AS VARCHAR) AS water_name,
    CAST(geom AS GEOMETRY) AS geometry
  FROM read_parquet('${OUT_DIR}/water_areas_raw.parquet')
  WHERE geometry IS NOT NULL
),
risk_bands AS (
  SELECT
    osm_id,
    code,
    source_fclass,
    water_name,
    CASE
      WHEN source_fclass IN ('water', 'reservoir') THEN 'high'
      WHEN source_fclass IN ('riverbank', 'wetland') THEN 'medium'
      ELSE 'low'
    END AS flood_risk_level,
    geometry
  FROM water
)
SELECT
  osm_id,
  code,
  source_fclass,
  water_name,
  flood_risk_level,
  COALESCE(NULLIF(TRIM(water_name), ''), 'Unnamed water area') AS name,
  geometry,
  STRUCT_PACK(
    xmin := CAST(ST_XMin(geometry) AS FLOAT),
    ymin := CAST(ST_YMin(geometry) AS FLOAT),
    xmax := CAST(ST_XMax(geometry) AS FLOAT),
    ymax := CAST(ST_YMax(geometry) AS FLOAT)
  ) AS geometry_bbox
FROM risk_bands
WHERE geometry IS NOT NULL
) TO '${OUT_DIR}/flood_zones.parquet'
(FORMAT PARQUET, COMPRESSION '${COMPRESSION}');

COPY (
WITH settlements AS (
  SELECT
    CAST(osm_id AS VARCHAR) AS osm_id,
    CAST(code AS INTEGER) AS code,
    CAST(fclass AS VARCHAR) AS fclass,
    CAST(population AS BIGINT) AS population,
    CAST(name AS VARCHAR) AS name,
    CAST(geom AS GEOMETRY) AS geometry,
    'settlement' AS place_source,
    0 AS src_priority
  FROM read_parquet('${OUT_DIR}/places_raw.parquet')
  WHERE geometry IS NOT NULL
),
pois AS (
  SELECT
    CAST(osm_id AS VARCHAR) AS osm_id,
    CAST(code AS INTEGER) AS code,
    CAST(fclass AS VARCHAR) AS fclass,
    NULL::BIGINT AS population,
    CAST(name AS VARCHAR) AS name,
    CAST(geom AS GEOMETRY) AS geometry,
    'poi' AS place_source,
    1 AS src_priority
  FROM read_parquet('${OUT_DIR}/pois_raw.parquet')
  WHERE geometry IS NOT NULL
),
unioned AS (
  SELECT * FROM settlements
  UNION ALL
  SELECT * FROM pois
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY osm_id
      ORDER BY
        CASE WHEN name IS NOT NULL AND TRIM(name) <> '' THEN 0 ELSE 1 END,
        src_priority
    ) AS rn
  FROM unioned
)
SELECT
  osm_id,
  code,
  fclass,
  population,
  name,
  place_source,
  geometry,
  STRUCT_PACK(
    xmin := CAST(ST_XMin(geometry) AS FLOAT),
    ymin := CAST(ST_YMin(geometry) AS FLOAT),
    xmax := CAST(ST_XMax(geometry) AS FLOAT),
    ymax := CAST(ST_YMax(geometry) AS FLOAT)
  ) AS geometry_bbox
FROM ranked
WHERE rn = 1
) TO '${OUT_DIR}/places.parquet'
(FORMAT PARQUET, COMPRESSION '${COMPRESSION}');
SQL

step "Verify outputs exist and look non-empty"
run bash -lc "for f in \"${OUT_DIR}/roads.parquet\" \"${OUT_DIR}/flood_zones.parquet\" \"${OUT_DIR}/places.parquet\"; do if [[ -s \"\$f\" ]]; then echo \"OK: \$f\"; else echo \"MISSING/EMPTY: \$f\"; exit 1; fi; done"

step "Report number of created GeoParquet files"
echo "+ created file count:"
run bash -lc "ls -1 \"${OUT_DIR}\"/*.parquet 2>/dev/null | wc -l"

step "Quick DuckDB counts (non-empty check)"
run duckdb :memory: <<SQL
SELECT 'roads' AS layer, COUNT(*) AS n FROM read_parquet('${OUT_DIR}/roads.parquet')
UNION ALL
SELECT 'flood_zones' AS layer, COUNT(*) AS n FROM read_parquet('${OUT_DIR}/flood_zones.parquet')
UNION ALL
SELECT 'places' AS layer, COUNT(*) AS n FROM read_parquet('${OUT_DIR}/places.parquet');
SQL

step "Cleanup intermediate raw parquet files"
run rm -f \
  "${OUT_DIR}/roads_raw.parquet" \
  "${OUT_DIR}/water_areas_raw.parquet" \
  "${OUT_DIR}/places_raw.parquet" \
  "${OUT_DIR}/pois_raw.parquet"

step "Done"
