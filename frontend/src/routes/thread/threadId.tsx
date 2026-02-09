import { useSuspenseQuery } from "@tanstack/react-query";
import {
	createFileRoute,
	Link,
	notFound,
	useNavigate,
} from "@tanstack/react-router";
import { Home } from "lucide-react";
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
import type { PlotPerfStats } from "./threadId/types";
import { useInvokeAgent } from "./threadId/useInvokeAgent";
import { usePlotController } from "./threadId/usePlotController";
import { useTelemetry } from "./threadId/useTelemetry";

export const Route = createFileRoute("/thread/$threadId")({
	params: {
		parse: (params) =>
			z.object({ threadId: z.coerce.number().int().positive() }).parse(params),
	},
	loader: async ({ params, context }) => {
		const scenarioId =
			window.localStorage.getItem("pange_scenario")?.trim() ||
			"prague_transport";
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
			"show layers",
			"how many pubs are flooded?",
			"find 20 dry pubs near metro",
			"recommend 5 safe pubs",
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
	const slowToastLastShownAtRef = useRef<number>(0);
	useEffect(() => {
		if (!slowToast) return;
		const t = window.setTimeout(() => setSlowToast(null), 10_000);
		return () => window.clearTimeout(t);
	}, [slowToast]);

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
					});
				if (best.total > 0) {
					layerMsg = `${best.layerId} (duck ${best.duck.toFixed(
						1,
					)}ms, decode ${best.dec.toFixed(1)}ms)`;
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

	const {
		plotContainerRef,
		plotData,
		setPlotData,
		mapView,
		setMapView,
		getViewportSize,
		getCurrentBbox,
		getStats,
		schedulePlotRefresh,
		abortPlotRefresh,
		setInvokeBusy,
		onRelayout,
	} = usePlotController({
		threadMessages: thread.messages,
		engine,
		scenarioId,
		onPlotRefreshStats: maybeShowSlowToast,
	});

	const [drawerOpen, setDrawerOpen] = useState(false);

	const { mutate, isPending, partialMessage, clearPartialMessage } =
		useInvokeAgent({
			threadId,
			engine,
			scenarioId,
			autoMinimizeChat,
			mapView,
			getCurrentBbox,
			getViewportSize,
			setPlotData,
			setMapView,
			abortPlotRefresh,
			setDrawerOpen,
			refetchThread: refetch,
		});

	useEffect(() => {
		setInvokeBusy(isPending || partialMessage !== null);
	}, [isPending, partialMessage, setInvokeBusy]);

	// When scenario changes, re-center to its default view (map-first mental model).
	useEffect(() => {
		let cancelled = false;
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
						schedulePlotRefresh({ center: nextCenter, zoom: nextZoom, bbox });
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
		schedulePlotRefresh,
		setMapView,
		setPlotData,
	]);

	const stats = getStats();

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
