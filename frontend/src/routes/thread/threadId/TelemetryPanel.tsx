import { Button } from "@/components/ui/button";
import { asRecord } from "./plotlyMapUtils";
import type { TelemetrySlowestRow, TelemetrySummaryRow } from "./types";

export function TelemetryPanel(props: {
	summary: TelemetrySummaryRow[];
	slowest: TelemetrySlowestRow[];
	onRefresh: () => void;
	onClose: () => void;
}) {
	const { summary, slowest, onRefresh, onClose } = props;
	const fmtZoom = (z: unknown) =>
		typeof z === "number" && Number.isFinite(z) ? z.toFixed(2) : "?";
	const fmtMs = (n: unknown) =>
		typeof n === "number" && Number.isFinite(n) ? n.toFixed(1) : "?";
	const bottleneckFromStats = (statsUnknown: unknown) => {
		const stats = asRecord(statsUnknown);
		const t = asRecord(stats?.timingsMs);
		const parts = [
			{ key: "engineGet", label: "get", v: t?.engineGet },
			{ key: "route", label: "route", v: t?.route },
			{ key: "lod", label: "lod", v: t?.lod },
			{ key: "plot", label: "plot", v: t?.plot },
			{ key: "jsonSerialize", label: "json", v: t?.jsonSerialize },
		].filter((p) => typeof p.v === "number") as {
			key: string;
			label: string;
			v: number;
		}[];
		const step = parts.length
			? parts.reduce((a, b) => (b.v > a.v ? b : a))
			: null;

		// GeoParquet per-layer timing (best-effort).
		const engineStats = asRecord(stats?.engineStats);
		const gp = asRecord(engineStats?.geoparquet);
		const layers = gp?.layers;
		const slowLayer =
			Array.isArray(layers) && layers.length > 0
				? (layers as unknown[])
						.map((x) => asRecord(x))
						.filter(Boolean)
						.map((l) => {
							const duck = typeof l?.duckdbMs === "number" ? l.duckdbMs : 0;
							const dec = typeof l?.decodeMs === "number" ? l.decodeMs : 0;
							return {
								layerId: typeof l?.layerId === "string" ? l.layerId : "?",
								total: duck + dec,
								duck,
								dec,
							};
						})
						.reduce((a, b) => (b.total > a.total ? b : a), {
							layerId: "?",
							total: 0,
							duck: 0,
							dec: 0,
						})
				: null;

		return { step, slowLayer };
	};

	return (
		<div className="absolute top-2 right-2 z-10 rounded-md border border-border bg-background/95 px-3 py-2 text-xs w-[420px] max-w-[90%] max-h-[85%] overflow-auto">
			<div className="flex items-center justify-between mb-2">
				<div className="font-semibold">Telemetry (DuckDB)</div>
				<div className="flex gap-2">
					<Button size="sm" variant="secondary" onClick={onRefresh}>
						Refresh
					</Button>
					<Button size="sm" variant="ghost" onClick={onClose}>
						Close
					</Button>
				</div>
			</div>

			<div className="text-muted-foreground mb-2">
				If the backend is running, prefer this panel/API. DuckDB telemetry DB is
				locked for external readers while the backend writes to it.
			</div>

			<div className="font-semibold mb-1">Summary</div>
			<div className="space-y-1 mb-3">
				{summary.map((row) => (
					<div
						key={`${row.engine}-${row.endpoint}`}
						className="border border-border rounded p-2"
					>
						<div className="text-foreground font-medium">
							{row.endpoint} ({row.engine}) n={row.n}
						</div>
						<div className="text-muted-foreground">
							total ms: p50 {row.p50TotalMs?.toFixed?.(1) ?? "?"}, p95{" "}
							{row.p95TotalMs?.toFixed?.(1) ?? "?"}, p99{" "}
							{row.p99TotalMs?.toFixed?.(1) ?? "?"}
						</div>
						<div className="text-muted-foreground">
							cache hit: {row.cacheHitRate?.toFixed?.(2) ?? "?"}, avg payload:{" "}
							{row.avgPayloadKB?.toFixed?.(1) ?? "?"}KB
						</div>
					</div>
				))}
				{summary.length === 0 && (
					<div className="text-muted-foreground">No telemetry rows yet.</div>
				)}
			</div>

			<div className="font-semibold mb-1">Slowest</div>
			<div className="space-y-1">
				{slowest.map((r) => {
					const b = bottleneckFromStats(r.stats);
					return (
						<div
							key={`${r.tsMs}-${r.endpoint}`}
							className="border border-border rounded p-2"
						>
							<div className="text-foreground font-medium">
								{r.endpoint} total {fmtMs(r.totalMs)}ms (zoom{" "}
								{fmtZoom(r.viewZoom)})
							</div>
							<div className="text-muted-foreground">
								payload {r.payloadKB?.toFixed?.(1) ?? "?"}KB, cache{" "}
								{r.cacheHit === true
									? "hit"
									: r.cacheHit === false
										? "miss"
										: "?"}
							</div>
							{b.step && (
								<div className="text-muted-foreground">
									step bottleneck: {b.step.label} {fmtMs(b.step.v)}ms
								</div>
							)}
							{b.slowLayer && b.slowLayer.total > 0 ? (
								<div className="text-muted-foreground">
									slowest layer: {b.slowLayer.layerId} (duck{" "}
									{fmtMs(b.slowLayer.duck)}
									ms, decode {fmtMs(b.slowLayer.dec)}ms)
								</div>
							) : null}
						</div>
					);
				})}
				{slowest.length === 0 && (
					<div className="text-muted-foreground">No slow rows yet.</div>
				)}
			</div>
		</div>
	);
}
