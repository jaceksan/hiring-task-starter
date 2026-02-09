import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PlotParams } from "react-plotly.js";
import {
	asRecord,
	calcBboxFromCenterZoom,
	getLayoutMeta,
	getMapboxCenter,
	getMapboxZoom,
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
	onPlotRefreshStats?: (stats: PlotPerfStats | null) => void;
}) {
	const { threadMessages, engine, scenarioId, onPlotRefreshStats } = args;

	const plotContainerRef = useRef<HTMLDivElement | null>(null);
	const plotRefreshTimeoutRef = useRef<number | null>(null);
	const plotRefreshAbortRef = useRef<AbortController | null>(null);
	const lastPlotRefreshKeyRef = useRef<string | null>(null);
	const invokeBusyRef = useRef(false);
	const relayoutRafRef = useRef<number | null>(null);

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

	// Keep a ref so schedulePlotRefresh can read the latest highlight without
	// having currentHighlight in its dependency array. This prevents a cascade:
	// zoom → setPlotData → currentHighlight changes → schedulePlotRefresh changes
	// → scenario-centering useEffect re-fires → snaps map back to default view.
	const currentHighlightRef = useRef(currentHighlight);
	useEffect(() => {
		currentHighlightRef.current = currentHighlight;
	}, [currentHighlight]);

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

			// Important: abort any in-flight request immediately on new interaction.
			// Otherwise a stale response can arrive and "snap back" the map view.
			plotRefreshAbortRef.current?.abort();
			plotRefreshAbortRef.current = null;

			if (plotRefreshTimeoutRef.current !== null) {
				window.clearTimeout(plotRefreshTimeoutRef.current);
			}
			plotRefreshTimeoutRef.current = window.setTimeout(async () => {
				const ac = new AbortController();
				plotRefreshAbortRef.current = ac;
				const requestKey = key;
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
							highlight: currentHighlightRef.current(),
							engine,
							scenarioId,
						}),
						signal: ac.signal,
					});
					// Ignore stale responses (can happen if user pans/zooms quickly).
					if (lastPlotRefreshKeyRef.current !== requestKey) return;
					if (!resp.ok) return;
					const payload = (await resp.json()) as Pick<
						PlotParams,
						"data" | "layout"
					>;
					if (lastPlotRefreshKeyRef.current !== requestKey) return;
					if (ac.signal.aborted) return;

					// Emit backend stats for UX (toast) and debugging.
					try {
						const layout = asRecord(payload.layout);
						const meta = layout ? asRecord(layout.meta) : null;
						const stats = meta ? (meta.stats as PlotPerfStats) : null;
						onPlotRefreshStats?.(stats ?? null);
					} catch {
						onPlotRefreshStats?.(null);
					}

					// Apply new traces + meta from the backend, but NEVER override
					// the current mapbox view (zoom/center). Plotly.react() applies
					// explicit layout.mapbox.zoom/center values which would "snap
					// back" the map to whatever the backend sent. Instead, keep
					// mapbox view management purely in userland (onRelayout → state).
					setPlotData((prev) => {
						const prevLayout = asRecord(prev.layout) ?? {};
						const prevMb = asRecord(prevLayout.mapbox) ?? {};
						const respLayout = asRecord(payload.layout) ?? {};
						const respMb = asRecord(respLayout.mapbox) ?? {};
						return {
							data: payload.data,
							layout: {
								...respLayout,
								mapbox: {
									...respMb,
									// Preserve current view — do not let the backend
									// response override the user's zoom/pan position.
									center: (prevMb.center ?? respMb.center) as
										| Record<string, number>
										| undefined,
									zoom: (prevMb.zoom ?? respMb.zoom) as number | undefined,
								},
							},
						} as Pick<PlotParams, "data" | "layout">;
					});
				} catch {
					// ignore abort/network errors
				}
			}, 250);
		},
		[engine, getViewportSize, onPlotRefreshStats, scenarioId],
	);

	const readViewFromPlotDom = useCallback((): {
		center: MapCenter | null;
		zoom: number | null;
	} => {
		const container = plotContainerRef.current;
		const plotEl = container?.querySelector?.(".js-plotly-plot") ?? null;
		const plotR = plotEl
			? (plotEl as unknown as Record<string, unknown>)
			: null;
		const fullLayout = plotR ? asRecord(plotR._fullLayout) : null;
		const mapbox = fullLayout ? asRecord(fullLayout.mapbox) : null;
		const subplot = mapbox ? asRecord(mapbox._subplot) : null;
		const mapMaybe = subplot?.map;
		const map =
			mapMaybe && typeof mapMaybe === "object"
				? (mapMaybe as {
						getCenter?: () => unknown;
						getZoom?: () => unknown;
					})
				: null;
		if (map?.getCenter && map?.getZoom) {
			const c = asRecord(map.getCenter());
			const z = map.getZoom();
			const lat = typeof c?.lat === "number" ? c.lat : null;
			const lon = typeof c?.lng === "number" ? c.lng : null;
			return {
				center: lat !== null && lon !== null ? { lat, lon } : null,
				zoom: typeof z === "number" ? z : null,
			};
		}

		const c = asRecord(mapbox?.center);
		return {
			center:
				typeof c?.lat === "number" && typeof c?.lon === "number"
					? { lat: c.lat, lon: c.lon }
					: null,
			zoom: typeof mapbox?.zoom === "number" ? mapbox.zoom : null,
		};
	}, []);

	const getAuthoritativeMapContext = useCallback(() => {
		const domView = readViewFromPlotDom();
		if (!domView.center || typeof domView.zoom !== "number") return null;
		const viewport = getViewportSize();
		const bbox = viewport
			? calcBboxFromCenterZoom(domView.center, domView.zoom, viewport)
			: null;
		return {
			center: domView.center,
			zoom: domView.zoom,
			bbox,
			viewport,
		};
	}, [getViewportSize, readViewFromPlotDom]);

	const applyUserView = useCallback(
		(next: { center: MapCenter; zoom: number }) => {
			const prev = mapViewRef.current;
			const EPS_CENTER = 1e-7;
			const EPS_ZOOM = 1e-6;
			const unchanged =
				Math.abs(next.center.lat - prev.center.lat) < EPS_CENTER &&
				Math.abs(next.center.lon - prev.center.lon) < EPS_CENTER &&
				Math.abs(next.zoom - prev.zoom) < EPS_ZOOM;
			if (unchanged) return;

			const viewport = getViewportSize();
			const bbox = viewport
				? calcBboxFromCenterZoom(next.center, next.zoom, viewport)
				: prev.bbox;

			// Only update our internal view tracking + trigger a backend refresh.
			// We deliberately do NOT call setPlotData here — Plotly already knows
			// about the new view (it's the source of the relayout event).
			// Calling setPlotData would trigger a React re-render → Plotly.react()
			// with explicit zoom/center, which can "snap back" the map.
			setMapView({ center: next.center, zoom: next.zoom, bbox });
			if (bbox)
				schedulePlotRefresh({ center: next.center, zoom: next.zoom, bbox });
		},
		[getViewportSize, schedulePlotRefresh],
	);

	const onRelayout = useCallback(() => {
		// Relayout payload for Mapbox interactions can be incomplete or vary by Plotly version.
		// Read the authoritative view from the Mapbox instance on the next animation frame
		// (after interaction is applied), then sync React state from that.
		if (relayoutRafRef.current !== null) {
			window.cancelAnimationFrame(relayoutRafRef.current);
		}
		relayoutRafRef.current = window.requestAnimationFrame(() => {
			relayoutRafRef.current = null;
			const domView = readViewFromPlotDom();
			if (!domView.center || typeof domView.zoom !== "number") return;
			applyUserView({ center: domView.center, zoom: domView.zoom });
		});
	}, [applyUserView, readViewFromPlotDom]);

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

	useEffect(() => {
		return () => {
			if (relayoutRafRef.current !== null) {
				window.cancelAnimationFrame(relayoutRafRef.current);
				relayoutRafRef.current = null;
			}
		};
	}, []);

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
		getAuthoritativeMapContext,
		setInvokeBusy,
		onRelayout,
	};
}
