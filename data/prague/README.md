## Prague public test layers (for dev + testing)

This folder contains **small, reproducible public datasets** to develop and test the “Prague flood” demo.

### Layers

1. **Flood extent (Q100) – polygons**  
   - File: `prague_q100_flood.geojson`  
   - Source: IPR Praha (via National Open Data Catalog)  
   - Dataset page: `https://data.gov.cz/dataset?iri=https%3A%2F%2Fdata.gov.cz%2Fzdroj%2Fdatov%C3%A9-sady%2F70883858%2Ff3e6c4e83ac374189ac0343c498529f9`  
   - Direct GeoJSON download: `https://lkod-iprpraha.hub.arcgis.com/api/download/v1/items/c9dc5fa395b2478a8db0a7cc5be0e447/geojson?layers=0`

2. **Metro track geometry – lines**  
   - File: `prague_metro_ways_overpass.json`  
   - Source: OpenStreetMap via Overpass API  
   - Query: `way["railway"="subway"](49.94,14.22,50.18,14.70); out geom;`

3. **Metro stations + entrances – points**  
   - File: `prague_metro_stations_overpass.json`  
   - Source: OpenStreetMap via Overpass API  
   - Query (union):  
     - `nwr["railway"="station"]["station"="subway"](49.94,14.22,50.18,14.70);`  
     - `nwr["public_transport"="station"]["subway"="yes"](49.94,14.22,50.18,14.70);`  
     - `node["railway"="subway_entrance"](49.94,14.22,50.18,14.70);`  
     - `out center;`

4. **Tram track geometry – lines (optional)**  
   - File: `prague_tram_ways_overpass.json`  
   - Source: OpenStreetMap via Overpass API  
   - Query: `way["railway"="tram"](49.94,14.22,50.18,14.70); out geom;`

5. **Tram stops + platforms – points (optional)**  
   - File: `prague_tram_stops_overpass.json`  
   - Source: OpenStreetMap via Overpass API  
   - Query (union):  
     - `node["railway"="tram_stop"](49.94,14.22,50.18,14.70);`  
     - `nwr["public_transport"="platform"]["tram"="yes"](49.94,14.22,50.18,14.70);`  
     - `nwr["railway"="platform"]["tram"="yes"](49.94,14.22,50.18,14.70);`  
     - `out center;`

6. **Beer layer (pubs + biergartens + breweries) – points**  
   - File: `prague_beer_pois_overpass.json`  
   - Source: OpenStreetMap via Overpass API  
   - Query: `nwr["amenity"="biergarten"](49.94,14.22,50.18,14.70); nwr["amenity"="pub"](...); nwr["craft"="brewery"](...); out center;`

### Re-fetch

Run:

```bash
./scripts/fetch_prague_test_layers.sh
```

### Notes for later performance testing

These files are intentionally small. For performance proofs, prefer:
- a **larger AOI** (Czech Republic, EU) or a **higher-resolution** dataset, and
- server-side clipping/simplification before emitting Plotly traces.

