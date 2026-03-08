export type MapCenter = { lat: number; lon: number };

export type ViewportSize = { width: number; height: number };

export type FloodRiskLevel =
	| "extreme"
	| "very_high"
	| "high"
	| "medium"
	| "low"
	| "any";
export type PlaceCategoryId = string;
export type InspectMode = "auto" | "places" | "flood_zones" | "roads";

export type FloodSelectionStats = {
	mode?: "aoi" | "selected";
	riskLevel?: FloodRiskLevel;
	selectedCount?: number;
	activeZoneCount?: number;
};

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
	promptType?: string;
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
	promptType?: string;
	totalMs?: number;
	viewZoom?: number;
	payloadKB?: number;
	cacheHit?: boolean;
	stats?: unknown;
};

export type PlotPerfStats = {
	engine?: string;
	inspectMode?: InspectMode;
	promptType?: string;
	countStats?: {
		promptType?: string;
		floodedCount?: number;
		outsideCount?: number;
		approximate?: boolean;
		approximationReason?: string | null;
	};
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
	focusApplied?: boolean;
	timingsMs?: {
		total?: number;
		engineGet?: number;
		lod?: number;
		plot?: number;
		jsonSerialize?: number;
	};
	engineStats?: unknown;
	floodSelection?: FloodSelectionStats;
	placeControl?: {
		selectedCategories?: string[];
		availableCategories?: string[];
		activeCategories?: string[];
		beforeCount?: number;
		afterCount?: number;
	};
};
