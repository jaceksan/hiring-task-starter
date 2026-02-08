from __future__ import annotations

CREATE_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events (
  ts_ms BIGINT,
  endpoint TEXT,
  prompt TEXT,
  engine TEXT,
  view_zoom DOUBLE,
  aoi_min_lon DOUBLE,
  aoi_min_lat DOUBLE,
  aoi_max_lon DOUBLE,
  aoi_max_lat DOUBLE,
  stats_json TEXT
);
"""

SUMMARY_SQL_TEMPLATE = """
SELECT
  engine,
  endpoint,
  COUNT(*) AS n,
  AVG(try_cast(json_extract(stats_json, '$.timingsMs.total') AS DOUBLE)) AS avg_total_ms,
  quantile_cont(try_cast(json_extract(stats_json, '$.timingsMs.total') AS DOUBLE), 0.50) AS p50_total_ms,
  quantile_cont(try_cast(json_extract(stats_json, '$.timingsMs.total') AS DOUBLE), 0.95) AS p95_total_ms,
  quantile_cont(try_cast(json_extract(stats_json, '$.timingsMs.total') AS DOUBLE), 0.99) AS p99_total_ms,
  AVG(try_cast(json_extract(stats_json, '$.payloadBytes') AS DOUBLE)) AS avg_payload_bytes,
  AVG(CASE WHEN try_cast(json_extract(stats_json, '$.cache.cacheHit') AS BOOLEAN) THEN 1 ELSE 0 END) AS cache_hit_rate
FROM events
{where_sql}
GROUP BY engine, endpoint
ORDER BY engine, endpoint
"""

SLOWEST_SQL_TEMPLATE = """
SELECT
  ts_ms,
  engine,
  endpoint,
  try_cast(json_extract(stats_json, '$.timingsMs.total') AS DOUBLE) AS total_ms,
  try_cast(json_extract(stats_json, '$.payloadBytes') AS BIGINT) AS payload_bytes,
  try_cast(json_extract(stats_json, '$.cache.cacheHit') AS BOOLEAN) AS cache_hit,
  view_zoom
FROM events
WHERE {where_sql}
ORDER BY total_ms DESC
LIMIT ?
"""

INSERT_EVENTS_SQL = """
INSERT INTO events
  (ts_ms, endpoint, prompt, engine, view_zoom, aoi_min_lon, aoi_min_lat, aoi_max_lon, aoi_max_lat, stats_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
