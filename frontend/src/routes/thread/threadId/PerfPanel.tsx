import type { PlotPerfStats } from "./types";

export function PerfPanel(props: {
	stats: PlotPerfStats;
	fallbackEngine: string;
}) {
	const { stats, fallbackEngine } = props;

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
						ms:{" "}
						<span className="text-foreground">
							{stats.timingsMs.total ?? "?"}
						</span>{" "}
						(get {stats.timingsMs.engineGet ?? "?"}, lod{" "}
						{stats.timingsMs.lod ?? "?"}, plot {stats.timingsMs.plot ?? "?"})
					</div>
				)}
			</div>
		</div>
	);
}
