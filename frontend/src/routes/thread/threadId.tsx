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
