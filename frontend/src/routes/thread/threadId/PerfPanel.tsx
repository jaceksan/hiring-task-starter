import type { PlotPerfStats } from "./types";

export function PerfPanel(props: {
	stats: PlotPerfStats;
	fallbackEngine: string;
}) {
	const { stats, fallbackEngine } = props;
	const t = stats.timingsMs;
	// Note: timingsMs is backend-provided; keep rendering tolerant to missing fields.
	const parts = [
		{ k: "engineGet", label: "get", v: t?.engineGet },
		{ k: "lod", label: "lod", v: t?.lod },
		{ k: "plot", label: "plot", v: t?.plot },
		{ k: "jsonSerialize", label: "json", v: t?.jsonSerialize },
	].filter((p) => typeof p.v === "number") as {
		k: string;
		label: string;
		v: number;
	}[];
	const bottleneck = parts.length
		? parts.reduce((a, b) => (b.v > a.v ? b : a))
		: null;

	return (
		<div className="absolute top-2 left-2 z-10 rounded-md border border-border bg-background/90 px-3 py-2 text-xs max-w-[320px]">
			<div className="font-semibold mb-1">Perf</div>
			<div className="space-y-0.5 text-muted-foreground">
				<div>
					engine:{" "}
					<span className="text-foreground">
						{stats.engine ?? fallbackEngine}
					</span>
				</div>
				<div>
					markers:{" "}
					<span className="text-foreground">
						{stats.renderedMarkers ?? "?"}
					</span>{" "}
					(clusters:{" "}
					<span className="text-foreground">{stats.renderedClusters ?? 0}</span>
					)
				</div>
				<div>
					vertices:{" "}
					<span className="text-foreground">L{stats.lineVertices ?? "?"}</span>{" "}
					/{" "}
					<span className="text-foreground">P{stats.polyVertices ?? "?"}</span>
				</div>
				{stats.cache && (
					<div>
						cache:{" "}
						<span className="text-foreground">
							{stats.cache.cacheHit ? "hit" : "miss"}
						</span>{" "}
						(tiles {stats.cache.tilesUsed ?? "?"}, z{" "}
						{stats.cache.tileZoom ?? "?"}, zb {stats.cache.zoomBucket ?? "?"})
					</div>
				)}
				{typeof stats.payloadBytes === "number" && (
					<div>
						payload:{" "}
						<span className="text-foreground">
							{Math.round(stats.payloadBytes / 1024)}KB
						</span>
					</div>
				)}
				{stats.timingsMs && (
					<div>
						ms: <span className="text-foreground">{t?.total ?? "?"}</span> (get{" "}
						{t?.engineGet ?? "?"}, lod {t?.lod ?? "?"}, plot {t?.plot ?? "?"}
						{typeof t?.jsonSerialize === "number"
							? `, json ${t.jsonSerialize}`
							: ""}
						)
					</div>
				)}
				{bottleneck && (
					<div>
						bottleneck:{" "}
						<span className="text-foreground">
							{bottleneck.label} {bottleneck.v.toFixed(1)}ms
						</span>
					</div>
				)}
			</div>
		</div>
	);
}
