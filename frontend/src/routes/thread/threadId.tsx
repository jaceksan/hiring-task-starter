import { useSuspenseQuery } from "@tanstack/react-query";
import {
	createFileRoute,
	Link,
	notFound,
	useNavigate,
} from "@tanstack/react-router";
import { ChevronDown, ChevronUp, Home } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "react-plotly.js";
import z from "zod";
import { useAppUi } from "@/components/layout/AppUiContext";
import { Button } from "@/components/ui/button";
import { DB } from "@/lib/db";
import { QUERIES } from "@/lib/queries";
import { isFailure } from "@/lib/result";
import { ChatDrawer } from "./threadId/ChatDrawer";
import { PerfPanel } from "./threadId/PerfPanel";
import { asRecord, calcBboxFromCenterZoom } from "./threadId/plotlyMapUtils";
import { TelemetryPanel } from "./threadId/TelemetryPanel";
import type {
	FloodRiskLevel,
	InspectMode,
	PlaceCategoryId,
	PlotPerfStats,
} from "./threadId/types";
import { useInvokeAgent } from "./threadId/useInvokeAgent";
import { usePlotController } from "./threadId/usePlotController";
import { useTelemetry } from "./threadId/useTelemetry";

const FLOOD_RISK_LEVELS: { id: FloodRiskLevel; label: string }[] = [
	{ id: "extreme", label: "Extreme" },
	{ id: "very_high", label: "Very high+" },
	{ id: "high", label: "High+" },
	{ id: "medium", label: "Medium+" },
	{ id: "any", label: "All risks" },
];
const INSPECT_MODES: { id: InspectMode; label: string }[] = [
	{ id: "auto", label: "Auto" },
	{ id: "places", label: "Places" },
	{ id: "flood_zones", label: "Flood zones" },
	{ id: "roads", label: "Roads" },
];

const PRETTY_PLACE_CATEGORY_LABELS: Record<string, string> = {
	capital: "Capital",
	urban: "Urban",
	suburban_rural: "Suburban/Rural",
	local_small: "Local/Small",
	other_settlement: "Other settlements",
	food_drink: "Food & Drink",
	health: "Health",
	education: "Education",
	transport: "Transport",
	shopping: "Shopping",
	tourism_culture: "Tourism/Culture",
	sport_leisure: "Sport/Leisure",
	public_services: "Public services",
	worship: "Worship",
	other_poi: "Other POIs",
};
const DEFAULT_PLACE_CATEGORIES = Object.keys(PRETTY_PLACE_CATEGORY_LABELS);

function prettyPlaceCategoryLabel(id: string): string {
	return (
		PRETTY_PLACE_CATEGORY_LABELS[id] ??
		id.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())
	);
}

export const Route = createFileRoute("/thread/$threadId")({
	params: {
		parse: (params) =>
			z.object({ threadId: z.coerce.number().int().positive() }).parse(params),
	},
	loader: async ({ params, context }) => {
		const scenarioId =
			window.localStorage.getItem("pange_scenario")?.trim() ||
			"prague_population_infrastructure_small";
		try {
			await context.queryClient.ensureQueryData(
				QUERIES.threads.detail(scenarioId, params.threadId),
			);
		} catch (error) {
			if (typeof error === "string") {
				if (error === "NOT_FOUND") {
					throw notFound();
				}

				throw new Error(error);
			}

			throw error;
		}
	},
	component: RouteComponent,
	notFoundComponent: NotFoundComponent,
});

function RouteComponent() {
	const navigate = useNavigate();
	const { threadId } = Route.useParams();

	const {
		scenarioId,
		engine,
		telemetryOpen,
		setTelemetryOpen,
		autoMinimizeChat,
	} = useAppUi();

	// Important: thread IDs are scenario-scoped in local storage.
	// If scenario changes while staying on the thread route, navigate away to avoid collisions.
	const initialScenarioIdRef = useRef(scenarioId);
	useEffect(() => {
		if (initialScenarioIdRef.current !== scenarioId) {
			navigate({ to: "/" });
		}
	}, [navigate, scenarioId]);

	const { data: thread, refetch } = useSuspenseQuery(
		QUERIES.threads.detail(scenarioId, threadId),
	);

	const {
		summary: telemetrySummary,
		slowest: telemetrySlowest,
		loadTelemetry,
	} = useTelemetry(engine, telemetryOpen);

	const defaultExamplePrompts = useMemo(
		() => [
			"how many places are flooded?",
			"show me escape roads for places in flood zone",
			"show safest nearby places outside selected flood risk with reachable roads",
		],
		[],
	);
	const [examplePrompts, setExamplePrompts] = useState<string[]>(
		defaultExamplePrompts,
	);

	const [slowToast, setSlowToast] = useState<{
		count: number;
		title: string;
		body: string;
	} | null>(null);
	const [floodRiskLevel, setFloodRiskLevel] = useState<FloodRiskLevel>("any");
	const [selectedFloodZoneIds, setSelectedFloodZoneIds] = useState<string[]>(
		[],
	);
	const [selectedPlaceCategories, setSelectedPlaceCategories] = useState<
		PlaceCategoryId[]
	>(DEFAULT_PLACE_CATEGORIES);
	const [inspectMode, setInspectMode] = useState<InspectMode>("auto");
	const [knownPlaceCategories, setKnownPlaceCategories] = useState<
		PlaceCategoryId[]
	>(DEFAULT_PLACE_CATEGORIES);
	const slowToastLastShownAtRef = useRef<number>(0);
	useEffect(() => {
		if (!slowToast) return;
		const t = window.setTimeout(() => setSlowToast(null), 10_000);
		return () => window.clearTimeout(t);
	}, [slowToast]);
	const placeCategoryResetKey = scenarioId;
	useEffect(() => {
		// Per scenario: show all categories by default.
		void placeCategoryResetKey;
		setKnownPlaceCategories(DEFAULT_PLACE_CATEGORIES);
		setSelectedPlaceCategories(DEFAULT_PLACE_CATEGORIES);
	}, [placeCategoryResetKey]);

	const maybeShowSlowToast = useMemo(() => {
		return (stats: PlotPerfStats | null) => {
			const t = stats?.timingsMs;
			const total = typeof t?.total === "number" ? t.total : null;
			if (total === null || total <= 250) return;

			// step bottleneck (best-effort)
			const parts = [
				{ label: "get", v: t?.engineGet },
				{ label: "lod", v: t?.lod },
				{ label: "plot", v: t?.plot },
				{ label: "json", v: t?.jsonSerialize },
			].filter((p) => typeof p.v === "number") as {
				label: string;
				v: number;
			}[];
			const step = parts.length
				? parts.reduce((a, b) => (b.v > a.v ? b : a))
				: null;

			// layer bottleneck (GeoParquet best-effort)
			const s = asRecord(stats?.engineStats);
			const gp = asRecord(s?.geoparquet);
			const layers = gp?.layers;
			let layerMsg: string | null = null;
			if (Array.isArray(layers) && layers.length > 0) {
				const best = (layers as unknown[])
					.map((x) => asRecord(x))
					.filter(Boolean)
					.map((l) => {
						const duck = typeof l?.duckdbMs === "number" ? l.duckdbMs : 0;
						const dec = typeof l?.decodeMs === "number" ? l.decodeMs : 0;
						const cap = asRecord(l?.cap);
						const effective =
							typeof cap?.effectiveLimit === "number"
								? cap.effectiveLimit
								: null;
						const cappedBy = Array.isArray(cap?.cappedBy)
							? ((cap.cappedBy as unknown[]).filter(
									(x) => typeof x === "string",
								) as string[])
							: [];
						return {
							layerId: typeof l?.layerId === "string" ? l.layerId : "?",
							total: duck + dec,
							duck,
							dec,
							effectiveLimit: effective,
							cappedBy,
						};
					})
					.reduce((a, b) => (b.total > a.total ? b : a), {
						layerId: "?",
						total: 0,
						duck: 0,
						dec: 0,
						effectiveLimit: null as number | null,
						cappedBy: [] as string[],
					});
				if (best.total > 0) {
					const capMsg =
						typeof best.effectiveLimit === "number"
							? ` • cap ${best.effectiveLimit}${
									best.cappedBy.length > 0
										? ` (${best.cappedBy.join("+")})`
										: ""
								}`
							: "";
					layerMsg = `${best.layerId} (duck ${best.duck.toFixed(
						1,
					)}ms, decode ${best.dec.toFixed(1)}ms)${capMsg}`;
				}
			}

			const now = Date.now();
			const withinBurst = now - slowToastLastShownAtRef.current < 1500;
			slowToastLastShownAtRef.current = now;
			setSlowToast((prev) => {
				const nextCount = withinBurst ? (prev?.count ?? 0) + 1 : 1;
				const prefix =
					nextCount > 1 ? `Slow refresh (x${nextCount})` : "Slow refresh";
				return {
					count: nextCount,
					title: `${prefix}: ${total.toFixed(1)}ms`,
					body: [
						step
							? `step bottleneck: ${step.label} ${step.v.toFixed(1)}ms`
							: null,
						layerMsg ? `slowest layer: ${layerMsg}` : null,
					]
						.filter(Boolean)
						.join(" • "),
				};
			});
		};
	}, []);
	const onPlotRefreshStats = useMemo(() => {
		return (stats: PlotPerfStats | null) => {
			maybeShowSlowToast(stats);
		};
	}, [maybeShowSlowToast]);

	const {
		plotContainerRef,
		plotData,
		setPlotData,
		mapView,
		setMapView,
		getViewportSize,
		getCurrentBbox,
		getAuthoritativeMapContext,
		getStats,
		schedulePlotRefresh,
		clearPromptHighlights,
		abortPlotRefresh,
		suppressPlotRefresh,
		setInvokeBusy,
		onRelayout,
	} = usePlotController({
		threadMessages: thread.messages,
		engine,
		scenarioId,
		floodRiskLevel,
		selectedFloodZoneIds,
		selectedPlaceCategories,
		inspectMode,
		roadHighlightTypes: [],
		onPlotRefreshStats,
	});
	const schedulePlotRefreshRef = useRef(schedulePlotRefresh);
	useEffect(() => {
		schedulePlotRefreshRef.current = schedulePlotRefresh;
	}, [schedulePlotRefresh]);

	const [drawerOpen, setDrawerOpen] = useState(false);
	const [controlsOpen, setControlsOpen] = useState(true);

	const { mutate, isPending, partialMessage, clearPartialMessage } =
		useInvokeAgent({
			threadId,
			engine,
			scenarioId,
			floodRiskLevel,
			selectedFloodZoneIds,
			selectedPlaceCategories,
			inspectMode,
			autoMinimizeChat,
			mapView,
			getCurrentBbox,
			getViewportSize,
			getAuthoritativeMapContext,
			setPlotData,
			setMapView,
			abortPlotRefresh,
			suppressPlotRefresh,
			setDrawerOpen,
			refetchThread: refetch,
		});

	useEffect(() => {
		setInvokeBusy(isPending || partialMessage !== null);
	}, [isPending, partialMessage, setInvokeBusy]);

	// When scenario changes, re-center to its default view (map-first mental model).
	useEffect(() => {
		let cancelled = false;
		setSelectedFloodZoneIds((prev) => (prev.length === 0 ? prev : []));
		(async () => {
			try {
				const resp = await fetch("http://localhost:8000/scenarios");
				if (!resp.ok) return;
				const raw = (await resp.json()) as unknown;
				const list = Array.isArray(raw) ? raw : [];
				const match = list.find((s) => {
					const r = asRecord(s);
					return r?.id === scenarioId;
				});
				const mr = asRecord(match);
				const dv = asRecord(mr?.defaultView);
				const prompts = mr?.examplePrompts;
				const center = dv ? asRecord(dv.center) : null;
				const zoom = dv?.zoom;
				if (
					Array.isArray(prompts) &&
					prompts.length > 0 &&
					prompts.every((p: unknown) => typeof p === "string") &&
					!cancelled
				) {
					setExamplePrompts(prompts as string[]);
				} else if (!cancelled) {
					setExamplePrompts(defaultExamplePrompts);
				}
				if (
					center &&
					typeof center.lat === "number" &&
					typeof center.lon === "number" &&
					typeof zoom === "number" &&
					!cancelled
				) {
					const viewport = getViewportSize();
					const nextCenter = { lat: center.lat, lon: center.lon };
					const nextZoom = zoom as number;
					const bbox = viewport
						? calcBboxFromCenterZoom(nextCenter, nextZoom, viewport)
						: null;
					setMapView({ center: nextCenter, zoom: nextZoom, bbox });
					setPlotData((prev) => {
						const layout = asRecord(prev.layout) ?? {};
						const mb = asRecord(layout.mapbox) ?? {};
						return {
							...prev,
							layout: {
								...layout,
								mapbox: { ...mb, center: nextCenter, zoom: nextZoom },
							},
						};
					});
					if (bbox) {
						schedulePlotRefreshRef.current({
							center: nextCenter,
							zoom: nextZoom,
							bbox,
						});
					}
				}
			} catch {
				// ignore
			}
		})();
		return () => {
			cancelled = true;
		};
	}, [
		defaultExamplePrompts,
		scenarioId,
		getViewportSize,
		setMapView,
		setPlotData,
	]);

	const stats = getStats();
	const floodSelection = stats?.floodSelection;
	const placeControl = stats?.placeControl;
	const availablePlaceCategories = useMemo(
		() =>
			(placeControl?.availableCategories ?? []).filter(
				(x): x is string => typeof x === "string" && x.length > 0,
			),
		[placeControl?.availableCategories],
	);
	useEffect(() => {
		// Keep category list stable across zoom changes: merge newly discovered categories,
		// never shrink on AOI refresh.
		if (availablePlaceCategories.length === 0) return;
		setKnownPlaceCategories((prev) => {
			const setPrev = new Set(prev);
			const extras = availablePlaceCategories.filter((x) => !setPrev.has(x));
			if (extras.length === 0) return prev;
			return [...prev, ...extras];
		});
	}, [availablePlaceCategories]);

	const floodMode =
		floodSelection?.mode ?? (selectedFloodZoneIds.length ? "selected" : "aoi");
	const floodModeCount =
		typeof floodSelection?.activeZoneCount === "number"
			? floodSelection.activeZoneCount
			: floodMode === "selected"
				? selectedFloodZoneIds.length
				: 0;

	const refreshUsingCurrentView = (
		overrides?: Partial<{
			floodRiskLevel: FloodRiskLevel;
			selectedFloodZoneIds: string[];
			selectedPlaceCategories: PlaceCategoryId[];
			inspectMode: InspectMode;
		}>,
		opts?: { keepHighlights?: boolean },
	) => {
		const keepHighlights = opts?.keepHighlights ?? true;
		if (!keepHighlights) {
			clearPromptHighlights();
		}
		const authoritative = getAuthoritativeMapContext();
		const center = authoritative?.center ?? mapView.center;
		const zoom = authoritative?.zoom ?? mapView.zoom;
		const bbox = authoritative?.bbox ?? mapView.bbox;
		if (!bbox) return;
		schedulePlotRefresh({
			center,
			zoom,
			bbox,
			floodRiskLevel: overrides?.floodRiskLevel ?? floodRiskLevel,
			selectedFloodZoneIds:
				overrides?.selectedFloodZoneIds ?? selectedFloodZoneIds,
			selectedPlaceCategories:
				overrides?.selectedPlaceCategories ?? selectedPlaceCategories,
			inspectMode: overrides?.inspectMode ?? inspectMode,
			highlightsOverride: keepHighlights ? undefined : [],
		});
	};

	return (
		<div className="w-full h-full">
			<div
				ref={plotContainerRef}
				className="w-full h-full flex justify-center items-center bg-accent relative"
			>
				{slowToast && (
					<div className="absolute top-2 left-1/2 -translate-x-1/2 z-20 w-[520px] max-w-[92%] rounded-md border border-border bg-background/95 px-3 py-2 text-xs shadow">
						<div className="flex items-start justify-between gap-3">
							<div>
								<div className="font-semibold">{slowToast.title}</div>
								{slowToast.body && (
									<div className="text-muted-foreground mt-0.5">
										{slowToast.body}
									</div>
								)}
							</div>
							<Button
								size="sm"
								variant="ghost"
								className="h-7 px-2"
								onClick={() => setSlowToast(null)}
							>
								Close
							</Button>
						</div>
					</div>
				)}
				<div className="absolute right-3 top-3 z-20 w-[250px] rounded-md border border-border bg-background/95 px-3 py-2 text-xs shadow">
					<div className="mb-1 flex items-center justify-between gap-2">
						<div className="font-semibold">Filters</div>
						<Button
							size="sm"
							variant="ghost"
							className="h-6 px-2 text-[11px]"
							onClick={() => setControlsOpen((prev) => !prev)}
							title={controlsOpen ? "Collapse filters" : "Expand filters"}
						>
							{controlsOpen ? (
								<>
									Collapse <ChevronDown className="size-3" />
								</>
							) : (
								<>
									Expand <ChevronUp className="size-3" />
								</>
							)}
						</Button>
					</div>
					{controlsOpen && (
						<>
							<div>
								<div className="font-semibold">Inspect</div>
								<div className="text-muted-foreground mt-0.5 mb-2">
									Deterministic hover priority for map metadata.
								</div>
								<div className="space-y-1.5">
									{INSPECT_MODES.map((item) => (
										<label
											key={item.id}
											className="flex items-center justify-between gap-2 cursor-pointer"
										>
											<span>{item.label}</span>
											<input
												type="radio"
												name="inspect-mode"
												checked={inspectMode === item.id}
												onChange={() => {
													setInspectMode(item.id);
													refreshUsingCurrentView({ inspectMode: item.id });
												}}
											/>
										</label>
									))}
								</div>
							</div>
							<div className="mt-3 pt-2 border-t border-border">
								<div className="font-semibold">Flood risk</div>
								<div className="text-muted-foreground mt-0.5 mb-2">
									Used for flood-zone filtering in requests.
								</div>
								<div className="text-[11px] text-muted-foreground mb-2">
									Mode: {floodMode === "selected" ? "Selected" : "AOI"} (
									{floodModeCount})
								</div>
								<div className="space-y-1.5">
									{FLOOD_RISK_LEVELS.map((item) => (
										<label
											key={item.id}
											className="flex items-center justify-between gap-2 cursor-pointer"
										>
											<span>{item.label}</span>
											<input
												type="radio"
												name="flood-risk-level"
												checked={floodRiskLevel === item.id}
												onChange={() => {
													setFloodRiskLevel(item.id);
													refreshUsingCurrentView(
														{ floodRiskLevel: item.id },
														{ keepHighlights: false },
													);
												}}
											/>
										</label>
									))}
								</div>
								{selectedFloodZoneIds.length > 0 && (
									<Button
										size="sm"
										variant="ghost"
										className="h-7 px-2 mt-2"
										onClick={() => {
											setSelectedFloodZoneIds([]);
											refreshUsingCurrentView(
												{ selectedFloodZoneIds: [] },
												{ keepHighlights: false },
											);
										}}
									>
										Clear selected zones ({selectedFloodZoneIds.length})
									</Button>
								)}
							</div>
							<div className="mt-3 pt-2 border-t border-border">
								<div className="font-semibold">Places</div>
								<div className="text-muted-foreground mt-0.5 mb-2">
									Show/hide place categories.
								</div>
								{knownPlaceCategories.length > 0 && (
									<div className="flex gap-1 mb-2">
										<Button
											size="sm"
											variant="ghost"
											className="h-6 px-2 text-[11px]"
											onClick={() => {
												setSelectedPlaceCategories([]);
												refreshUsingCurrentView(
													{ selectedPlaceCategories: [] },
													{ keepHighlights: false },
												);
											}}
										>
											None
										</Button>
										<Button
											size="sm"
											variant="ghost"
											className="h-6 px-2 text-[11px]"
											onClick={() => {
												setSelectedPlaceCategories([...knownPlaceCategories]);
												refreshUsingCurrentView(
													{
														selectedPlaceCategories: [...knownPlaceCategories],
													},
													{ keepHighlights: false },
												);
											}}
										>
											All
										</Button>
									</div>
								)}
								<div className="space-y-1.5">
									{knownPlaceCategories.map((item) => (
										<label
											key={item}
											className="flex items-center justify-between gap-2 cursor-pointer"
										>
											<span>{prettyPlaceCategoryLabel(item)}</span>
											<input
												type="checkbox"
												checked={selectedPlaceCategories.includes(item)}
												onChange={(e) => {
													const checked = e.currentTarget.checked;
													setSelectedPlaceCategories((prev) => {
														const next = new Set(prev);
														if (checked) next.add(item);
														else next.delete(item);
														const out = knownPlaceCategories.filter((id) =>
															next.has(id),
														);
														refreshUsingCurrentView(
															{
																selectedPlaceCategories: out,
															},
															{ keepHighlights: false },
														);
														return out;
													});
												}}
											/>
										</label>
									))}
								</div>
							</div>
						</>
					)}
				</div>
				{telemetryOpen && (
					<TelemetryPanel
						summary={telemetrySummary ?? []}
						slowest={telemetrySlowest ?? []}
						onRefresh={loadTelemetry}
						onClose={() => setTelemetryOpen(false)}
					/>
				)}
				{stats && <PerfPanel stats={stats} fallbackEngine={engine} />}
				<Plotly
					data={plotData.data}
					layout={{
						...plotData.layout,
						// Critical: preserve user pan/zoom across plot updates.
						// Without this, any re-render that supplies a new `layout` object (e.g. /plot refresh)
						// can reset the Mapbox view and make the map "snap back" immediately after zooming.
						uirevision: `${scenarioId}:${threadId}`,
						margin: { l: 0, r: 0, t: 0, b: 0 },
					}}
					config={{ scrollZoom: true, displayModeBar: false }}
					useResizeHandler={true}
					style={{ width: "100%", height: "100%" }}
					className="w-full h-full overflow-hidden"
					onRelayout={onRelayout}
					onClick={(event) => {
						const pt = event.points?.[0];
						const curveNumber =
							typeof pt?.curveNumber === "number" ? pt.curveNumber : -1;
						const trace =
							curveNumber >= 0
								? ((plotData.data?.[curveNumber] as Record<string, unknown>) ??
									null)
								: null;
						const traceName = typeof trace?.name === "string" ? trace.name : "";
						if (!traceName.startsWith("Flood zones (polygons)")) return;
						const customData = pt?.customdata;
						const zoneId =
							customData && typeof customData === "object"
								? (customData as { featureId?: unknown }).featureId
								: null;
						if (typeof zoneId !== "string" || zoneId.length === 0) return;
						setSelectedFloodZoneIds((prev) => {
							const next = new Set(prev);
							if (next.has(zoneId)) next.delete(zoneId);
							else next.add(zoneId);
							const out = [...next].sort();
							refreshUsingCurrentView(
								{ selectedFloodZoneIds: out },
								{ keepHighlights: false },
							);
							return out;
						});
					}}
				/>
			</div>

			<ChatDrawer
				open={drawerOpen}
				setOpen={setDrawerOpen}
				threadTitle={thread.title}
				threadCreatedAt={thread.createdAt}
				messages={thread.messages}
				examplePrompts={examplePrompts}
				partialMessage={partialMessage}
				disabled={isPending || partialMessage !== null}
				onClearMessages={async () => {
					const result = DB.threads.messages.clear(scenarioId, threadId);
					if (isFailure(result)) {
						console.error("ERROR_CLEARING_THREAD_MESSAGES", { result });
						return;
					}
					clearPartialMessage();
					await refetch();
				}}
				onSubmit={(message) => mutate(message)}
				onPromptClick={(prompt) => mutate(prompt)}
			/>
		</div>
	);
}

function NotFoundComponent() {
	const { threadId } = Route.useParams();

	return (
		<div className="min-h-screen flex flex-col gap-4 items-center justify-center bg-accent">
			<h1 className="font-bold text-3xl">Thread not found</h1>
			<div className="border border-border rounded-lg max-w-full bg-background p-4">
				Unfortunately we weren't able to find thread with ID: {threadId}
			</div>
			<div>
				<Button asChild size="lg" className="font-bold">
					<Link to="/">
						Go home
						<Home className="size-5" />
					</Link>
				</Button>
			</div>
		</div>
	);
}
