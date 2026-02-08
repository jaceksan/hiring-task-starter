import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PlotParams } from "react-plotly.js";
import {
	asRecord,
	calcBboxFromCenterZoom,
	getLayoutMeta,
	getMapboxCenter,
	getMapboxZoom,
	getRelayoutCenter,
	getRelayoutZoom,
} from "./plotlyMapUtils";
import type {
	BBox,
	MapCenter,
	MapViewState,
	PlotPerfStats,
	ViewportSize,
} from "./types";

type HighlightPayload = {
	layerId: string | null;
	featureIds: string[];
	title: string;
} | null;

export function usePlotController(args: {
	threadMessages: { data?: unknown }[];
	engine: string;
	scenarioId: string;
}) {
	const { threadMessages, engine, scenarioId } = args;

	const plotContainerRef = useRef<HTMLDivElement | null>(null);
	const plotRefreshTimeoutRef = useRef<number | null>(null);
	const plotRefreshAbortRef = useRef<AbortController | null>(null);
	const lastPlotRefreshKeyRef = useRef<string | null>(null);
	const invokeBusyRef = useRef(false);

	const [plotData, setPlotData] = useState<Pick<PlotParams, "data" | "layout">>(
		() => {
			const firstMessageWithData = threadMessages.find((message) =>
				Boolean(message.data),
			);
			const maybe = firstMessageWithData?.data as unknown;
			if (maybe && typeof maybe === "object") {
				return maybe as Pick<PlotParams, "data" | "layout">;
			}
			return {
				data: [{ type: "scattermapbox" }],
				layout: {
					mapbox: {
						center: { lat: 50.0755, lon: 14.4378 },
						zoom: 10.5,
						style: "carto-positron",
					},
				},
			};
		},
	);

	const initialCenter = useMemo<MapCenter>(() => {
		const center = getMapboxCenter(plotData.layout);
		return center ?? { lat: 50.0755, lon: 14.4378 };
	}, [plotData.layout]);

	const initialZoom = useMemo<number>(() => {
		const zoom = getMapboxZoom(plotData.layout);
		return typeof zoom === "number" ? zoom : 10.5;
	}, [plotData.layout]);

	const [mapView, setMapView] = useState<MapViewState>(() => ({
		center: initialCenter,
		zoom: initialZoom,
		bbox: null,
	}));

	const mapViewRef = useRef(mapView);
	useEffect(() => {
		mapViewRef.current = mapView;
	}, [mapView]);

	const setInvokeBusy = useCallback((busy: boolean) => {
		invokeBusyRef.current = busy;
	}, []);

	const getViewportSize = useCallback((): ViewportSize | null => {
		const el = plotContainerRef.current;
		if (!el) return null;
		const r = el.getBoundingClientRect();
		return {
			width: Math.max(1, Math.floor(r.width)),
			height: Math.max(1, Math.floor(r.height)),
		};
	}, []);

	const getCurrentBbox = useCallback((): BBox => {
		const mv = mapViewRef.current;
		if (mv.bbox) return mv.bbox;
		const viewport = getViewportSize();
		if (!viewport) {
			return {
				minLon: mv.center.lon - 0.05,
				minLat: mv.center.lat - 0.03,
				maxLon: mv.center.lon + 0.05,
				maxLat: mv.center.lat + 0.03,
			};
		}
		return calcBboxFromCenterZoom(mv.center, mv.zoom, viewport);
	}, [getViewportSize]);

	const currentHighlight = useCallback<() => HighlightPayload>(() => {
		const meta = asRecord(getLayoutMeta(plotData.layout));
		const h = meta ? asRecord(meta.highlight) : null;
		const ids = (h?.featureIds ?? h?.pointIds) as unknown;
		if (!h || !Array.isArray(ids) || ids.length === 0) return null;
		const layerId =
			typeof h.layerId === "string" && h.layerId.length > 0 ? h.layerId : null;
		const title =
			typeof h.title === "string" && h.title.length > 0
				? h.title
				: "Highlighted";
		return { layerId, featureIds: ids as string[], title };
	}, [plotData.layout]);

	const getStats = useCallback((): PlotPerfStats | null => {
		const meta = asRecord(getLayoutMeta(plotData.layout));
		return (meta?.stats as PlotPerfStats | null | undefined) ?? null;
	}, [plotData.layout]);

	const abortPlotRefresh = useCallback(() => {
		plotRefreshAbortRef.current?.abort();
		plotRefreshAbortRef.current = null;
		if (plotRefreshTimeoutRef.current !== null) {
			window.clearTimeout(plotRefreshTimeoutRef.current);
			plotRefreshTimeoutRef.current = null;
		}
	}, []);

	const schedulePlotRefresh = useCallback(
		(next: { center: MapCenter; zoom: number; bbox: BBox }) => {
			if (invokeBusyRef.current) return;

			const key = JSON.stringify({
				s: scenarioId,
				e: engine,
				z: Math.round(next.zoom * 10) / 10,
				b: {
					minLon: Math.round(next.bbox.minLon * 10_000) / 10_000,
					minLat: Math.round(next.bbox.minLat * 10_000) / 10_000,
					maxLon: Math.round(next.bbox.maxLon * 10_000) / 10_000,
					maxLat: Math.round(next.bbox.maxLat * 10_000) / 10_000,
				},
			});
			if (lastPlotRefreshKeyRef.current === key) return;
			lastPlotRefreshKeyRef.current = key;

			if (plotRefreshTimeoutRef.current !== null) {
				window.clearTimeout(plotRefreshTimeoutRef.current);
			}
			plotRefreshTimeoutRef.current = window.setTimeout(async () => {
				plotRefreshAbortRef.current?.abort();
				const ac = new AbortController();
				plotRefreshAbortRef.current = ac;
				try {
					const resp = await fetch("http://localhost:8000/plot", {
						method: "POST",
						headers: { "Content-Type": "application/json" },
						body: JSON.stringify({
							map: {
								bbox: next.bbox,
								view: { center: next.center, zoom: next.zoom },
								viewport: getViewportSize(),
							},
							highlight: currentHighlight(),
							engine,
							scenarioId,
						}),
						signal: ac.signal,
					});
					if (!resp.ok) return;
					const payload = (await resp.json()) as Pick<
						PlotParams,
						"data" | "layout"
					>;
					setPlotData(payload);
				} catch {
					// ignore abort/network errors
				}
			}, 250);
		},
		[currentHighlight, engine, getViewportSize, scenarioId],
	);

	const onRelayout = useCallback(
		(event: unknown) => {
			const e = event as Record<string, unknown>;
			const nextCenter = getRelayoutCenter(e);
			const nextZoom = getRelayoutZoom(e);

			setMapView((prev) => {
				const center =
					nextCenter &&
					typeof nextCenter.lat === "number" &&
					typeof nextCenter.lon === "number"
						? { lat: nextCenter.lat, lon: nextCenter.lon }
						: prev.center;
				const zoom = typeof nextZoom === "number" ? nextZoom : prev.zoom;
				const viewport = getViewportSize();
				const bbox = viewport
					? calcBboxFromCenterZoom(center, zoom, viewport)
					: prev.bbox;
				if (bbox) {
					schedulePlotRefresh({ center, zoom, bbox });
				}
				return { center, zoom, bbox };
			});
		},
		[getViewportSize, schedulePlotRefresh],
	);

	// Keep AOI bbox in sync when the map container is resized (e.g. chat drawer expand/collapse).
	useEffect(() => {
		const el = plotContainerRef.current;
		if (!el) return;
		const ro = new ResizeObserver(() => {
			const viewport = getViewportSize();
			if (!viewport) return;
			const { center, zoom } = mapViewRef.current;
			const bbox = calcBboxFromCenterZoom(center, zoom, viewport);
			setMapView((prev) => ({ ...prev, bbox }));
			schedulePlotRefresh({ center, zoom, bbox });
		});
		ro.observe(el);
		return () => ro.disconnect();
	}, [getViewportSize, schedulePlotRefresh]);

	return {
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
	};
}
