#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/data/prague"

mkdir -p "${OUT_DIR}"

echo "Fetching Prague Q100 flood extent (GeoJSON)..."
curl -L --fail -sS \
  'https://lkod-iprpraha.hub.arcgis.com/api/download/v1/items/c9dc5fa395b2478a8db0a7cc5be0e447/geojson?layers=0' \
  -o "${OUT_DIR}/prague_q100_flood.geojson"

# Prague-ish bbox used for the OSM layers.
# south,west,north,east
BBOX="49.94,14.22,50.18,14.70"

echo "Fetching beer POIs from Overpass..."
curl -L --fail -sS 'https://overpass-api.de/api/interpreter' \
  --data-urlencode "data=[out:json][timeout:60];(nwr[\"amenity\"=\"biergarten\"](${BBOX});nwr[\"amenity\"=\"pub\"](${BBOX});nwr[\"craft\"=\"brewery\"](${BBOX}););out center;" \
  -o "${OUT_DIR}/prague_beer_pois_overpass.json"

echo "Fetching metro ways from Overpass..."
curl -L --fail -sS 'https://overpass-api.de/api/interpreter' \
  --data-urlencode "data=[out:json][timeout:180];(way[\"railway\"=\"subway\"](${BBOX}););out geom;" \
  -o "${OUT_DIR}/prague_metro_ways_overpass.json"

echo "Fetching metro stations/entrances from Overpass..."
curl -L --fail -sS 'https://overpass-api.de/api/interpreter' \
  --data-urlencode "data=[out:json][timeout:180];(nwr[\"railway\"=\"station\"][\"station\"=\"subway\"](${BBOX});nwr[\"public_transport\"=\"station\"][\"subway\"=\"yes\"](${BBOX});node[\"railway\"=\"subway_entrance\"](${BBOX}););out center;" \
  -o "${OUT_DIR}/prague_metro_stations_overpass.json"

echo "Fetching tram ways from Overpass..."
curl -L --fail -sS 'https://overpass-api.de/api/interpreter' \
  --data-urlencode "data=[out:json][timeout:180];(way[\"railway\"=\"tram\"](${BBOX}););out geom;" \
  -o "${OUT_DIR}/prague_tram_ways_overpass.json"

echo "Fetching tram stops/platforms from Overpass..."
curl -L --fail -sS 'https://overpass-api.de/api/interpreter' \
  --data-urlencode "data=[out:json][timeout:180];(node[\"railway\"=\"tram_stop\"](${BBOX});nwr[\"public_transport\"=\"platform\"][\"tram\"=\"yes\"](${BBOX});nwr[\"railway\"=\"platform\"][\"tram\"=\"yes\"](${BBOX}););out center;" \
  -o "${OUT_DIR}/prague_tram_stops_overpass.json"

echo
echo "Done. Files in ${OUT_DIR}:"
ls -lh "${OUT_DIR}"

