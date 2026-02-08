export type MapCenter = { lat: number; lon: number };

export type ViewportSize = { width: number; height: number };

export type BBox = {
	minLon: number;
	minLat: number;
	maxLon: number;
	maxLat: number;
};

export type MapViewState = {
	center: MapCenter;
	zoom: number;
	bbox: BBox | null;
};

export type TelemetrySummaryRow = {
	engine?: string;
	endpoint?: string;
	n?: number;
	p50TotalMs?: number;
	p95TotalMs?: number;
	p99TotalMs?: number;
	cacheHitRate?: number;
	avgPayloadKB?: number;
};

export type TelemetrySlowestRow = {
	tsMs?: number;
	endpoint?: string;
	totalMs?: number;
	viewZoom?: number;
	payloadKB?: number;
	cacheHit?: boolean;
};

export type PlotPerfStats = {
	engine?: string;
	renderedMarkers?: number;
	renderedClusters?: number;
	lineVertices?: number;
	polyVertices?: number;
	payloadBytes?: number;
	cache?: {
		cacheHit?: boolean;
		tilesUsed?: number;
		tileZoom?: number;
		zoomBucket?: number;
	};
	timingsMs?: {
		total?: number;
		engineGet?: number;
		lod?: number;
		plot?: number;
	};
};
