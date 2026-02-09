import { useMutation } from "@tanstack/react-query";
import { EventSourceParserStream } from "eventsource-parser/stream";
import { useCallback, useState } from "react";
import type { PlotParams } from "react-plotly.js";
import { DB } from "@/lib/db";
import { isFailure } from "@/lib/result";
import { streamToAsyncGenerator } from "@/lib/streamToAsyncGenerator";
import {
	calcBboxFromCenterZoom,
	getMapboxCenter,
	getMapboxZoom,
} from "./plotlyMapUtils";
import type { BBox, MapViewState, ViewportSize } from "./types";

export function useInvokeAgent(args: {
	threadId: number;
	engine: string;
	scenarioId: string;
	autoMinimizeChat: boolean;
	mapView: MapViewState;
	getCurrentBbox: () => BBox;
	getViewportSize: () => ViewportSize | null;
	getAuthoritativeMapContext?: () => {
		center: { lat: number; lon: number };
		zoom: number;
		bbox: BBox | null;
		viewport: ViewportSize | null;
	} | null;
	setPlotData: (next: Pick<PlotParams, "data" | "layout">) => void;
	setMapView: (next: MapViewState) => void;
	abortPlotRefresh: () => void;
	setDrawerOpen: (open: boolean) => void;
	refetchThread: () => Promise<{ data?: unknown }>;
}) {
	const {
		threadId,
		engine,
		scenarioId,
		autoMinimizeChat,
		mapView,
		getCurrentBbox,
		getViewportSize,
		getAuthoritativeMapContext,
		setPlotData,
		setMapView,
		abortPlotRefresh,
		setDrawerOpen,
		refetchThread,
	} = args;

	const [partialMessage, setPartialMessage] = useState<string | null>(null);

	const clearPartialMessage = useCallback(() => {
		setPartialMessage(null);
	}, []);

	const mutation = useMutation({
		mutationKey: ["thread", scenarioId, threadId, "create-message"],
		mutationFn: async (text: string) => {
			const createMessageResult = DB.threads.messages.create(
				scenarioId,
				threadId,
				{
					text,
					author: "human",
				},
			);

			if (isFailure(createMessageResult)) {
				throw new Error(createMessageResult.error);
			}

			if (createMessageResult.data.id === 1) {
				DB.threads.updateTitle(scenarioId, threadId, text);
			}

			const { data: threadWithNewHumanMessage } = await refetchThread();
			if (!threadWithNewHumanMessage) {
				throw new Error("REFETCH_THREAD_RETURNED_NO_DATA");
			}

			// IMPORTANT: mapView state can lag behind the actual Mapbox view when the user
			// zooms/pans and immediately submits a prompt. Prefer the authoritative DOM view.
			const authoritative = getAuthoritativeMapContext?.() ?? null;
			const bbox = authoritative?.bbox ?? getCurrentBbox();
			const viewport = authoritative?.viewport ?? getViewportSize();
			const viewCenter = authoritative?.center ?? mapView.center;
			const viewZoom = authoritative?.zoom ?? mapView.zoom;
			const response = await fetch("http://localhost:8000/invoke", {
				method: "POST",
				body: JSON.stringify({
					...threadWithNewHumanMessage,
					map: {
						bbox,
						view: { center: viewCenter, zoom: viewZoom },
						viewport,
					},
					engine,
					scenarioId,
				}),
				headers: {
					"Content-Type": "application/json",
					Accept: "text/event-stream",
				},
			});

			if (!response.ok) {
				throw new Error("RESPONSE_NOT_OK", { cause: response });
			}

			if (!response.body) {
				throw new Error("RESPONSE_HAS_NO_BODY", { cause: response });
			}

			const stream = response.body
				.pipeThrough(new TextDecoderStream())
				.pipeThrough(new EventSourceParserStream());

			const generator = streamToAsyncGenerator(stream);

			let message = "";
			let data: unknown;
			setPartialMessage(message);

			for await (const event of generator) {
				switch (event.event) {
					case "append": {
						message += ` ${event.data}`;
						setPartialMessage(message);
						break;
					}

					case "commit": {
						message += event.data;
						// Persist the AI message text, but avoid storing huge Plotly payloads in localStorage.
						// Otherwise messages may "disappear" due to quota errors on save.
						const saveWithData = DB.threads.messages.create(
							scenarioId,
							threadId,
							{
								text: message,
								data,
								author: "ai",
							},
						);
						if (isFailure(saveWithData)) {
							const saveWithoutData = DB.threads.messages.create(
								scenarioId,
								threadId,
								{
									text: message,
									author: "ai",
								},
							);
							if (isFailure(saveWithoutData)) {
								throw new Error(saveWithoutData.error);
							}
						}
						// Important: don't clear the partial message until the thread data refreshes,
						// otherwise the answer can appear to "disappear" briefly (or permanently if refresh fails).
						await refetchThread();
						message = "";
						data = undefined;
						setPartialMessage(null);
						if (autoMinimizeChat) {
							setDrawerOpen(false);
						}
						break;
					}

					case "plot_data": {
						try {
							// If a background /plot refresh is in-flight, abort it. Otherwise it can
							// overwrite this authoritative plot update (e.g. highlights "flash" then disappear).
							abortPlotRefresh();

							const plot = JSON.parse(event.data) as Pick<
								PlotParams,
								"data" | "layout"
							>;
							// Storing Plotly payload per-message can exceed localStorage quota quickly.
							// Keep it in React state always; persist only if reasonably small.
							const MAX_PERSISTED_PLOT_CHARS = 200_000;
							data =
								event.data.length <= MAX_PERSISTED_PLOT_CHARS
									? plot
									: undefined;
							setPlotData(plot);

							const center = getMapboxCenter(plot.layout);
							const zoom = getMapboxZoom(plot.layout);
							if (center && typeof zoom === "number") {
								const vp = getViewportSize();
								setMapView({
									center: { lat: center.lat, lon: center.lon },
									zoom,
									bbox: vp ? calcBboxFromCenterZoom(center, zoom, vp) : null,
								});
							}
						} catch (error) {
							console.error("ERROR_PARSING_PLOT_DATA", { error, event });
						}
						break;
					}
				}
			}

			setPartialMessage(null);
		},
		onError: (error, variables) => {
			console.error(`${error.name}: ${error.message}`, error, variables);
		},
	});

	return {
		mutate: mutation.mutate,
		isPending: mutation.isPending,
		partialMessage,
		clearPartialMessage,
	};
}
