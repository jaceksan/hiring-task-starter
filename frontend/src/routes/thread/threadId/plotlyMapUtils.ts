import type { BBox, MapCenter, ViewportSize } from "./types";

export function asRecord(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object"
		? (value as Record<string, unknown>)
		: null;
}

export function getMapboxCenter(layout: unknown): MapCenter | null {
	const r = asRecord(layout);
	const mapbox = r ? asRecord(r.mapbox) : null;
	const center = mapbox ? asRecord(mapbox.center) : null;
	const lat = center?.lat;
	const lon = center?.lon;
	if (typeof lat === "number" && typeof lon === "number") return { lat, lon };
	return null;
}

export function getMapboxZoom(layout: unknown): number | null {
	const r = asRecord(layout);
	const mapbox = r ? asRecord(r.mapbox) : null;
	const zoom = mapbox?.zoom;
	return typeof zoom === "number" ? zoom : null;
}

export function getLayoutMeta(layout: unknown): unknown {
	const r = asRecord(layout);
	return r?.meta;
}

export function getRelayoutCenter(
	event: Record<string, unknown>,
): { lat: number; lon: number } | null {
	const direct = asRecord(event["mapbox.center"]);
	if (
		direct &&
		typeof direct.lat === "number" &&
		typeof direct.lon === "number"
	) {
		return { lat: direct.lat, lon: direct.lon };
	}
	const lat = event["mapbox.center.lat"];
	const lon = event["mapbox.center.lon"];
	if (typeof lat === "number" && typeof lon === "number") {
		return { lat, lon };
	}
	return null;
}

export function getRelayoutZoom(event: Record<string, unknown>): number | null {
	const z = event["mapbox.zoom"];
	return typeof z === "number" ? z : null;
}

export function calcBboxFromCenterZoom(
	center: MapCenter,
	zoom: number,
	viewport: ViewportSize,
): BBox {
	// Approximate Mapbox/Plotly viewport bounds using Web Mercator math.
	// This does not need to be perfect: a slightly-larger-than-visible bbox is fine for AOI clipping.
	const R = 6378137;
	const tileSize = 256;
	const lonRad = (center.lon * Math.PI) / 180;
	const latRad = (center.lat * Math.PI) / 180;
	const x = R * lonRad;
	const y = R * Math.log(Math.tan(Math.PI / 4 + latRad / 2));
	const metersPerPixel = (2 * Math.PI * R) / (tileSize * 2 ** zoom);

	const halfW = (viewport.width * metersPerPixel) / 2;
	const halfH = (viewport.height * metersPerPixel) / 2;

	const minX = x - halfW;
	const maxX = x + halfW;
	const minY = y - halfH;
	const maxY = y + halfH;

	const minLon = (minX / R) * (180 / Math.PI);
	const maxLon = (maxX / R) * (180 / Math.PI);
	const minLat =
		(2 * Math.atan(Math.exp(minY / R)) - Math.PI / 2) * (180 / Math.PI);
	const maxLat =
		(2 * Math.atan(Math.exp(maxY / R)) - Math.PI / 2) * (180 / Math.PI);

	return {
		minLon,
		minLat,
		maxLon,
		maxLat,
	};
}
