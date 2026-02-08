import { useCallback, useEffect, useState } from "react";
import { asRecord } from "./plotlyMapUtils";
import type { TelemetrySlowestRow, TelemetrySummaryRow } from "./types";

export function useTelemetry(engine: string, telemetryOpen: boolean) {
	const [summary, setSummary] = useState<TelemetrySummaryRow[] | null>(null);
	const [slowest, setSlowest] = useState<TelemetrySlowestRow[] | null>(null);

	const loadTelemetry = useCallback(async () => {
		try {
			const [sRaw, slowRaw] = await Promise.all([
				fetch(`http://localhost:8000/telemetry/summary?engine=${engine}`).then(
					(r) => r.json() as Promise<unknown>,
				),
				fetch(
					`http://localhost:8000/telemetry/slowest?engine=${engine}&limit=15`,
				).then((r) => r.json() as Promise<unknown>),
			]);
			const sRows = asRecord(sRaw)?.rows;
			const slowRows = asRecord(slowRaw)?.rows;
			setSummary(Array.isArray(sRows) ? (sRows as TelemetrySummaryRow[]) : []);
			setSlowest(
				Array.isArray(slowRows) ? (slowRows as TelemetrySlowestRow[]) : [],
			);
		} catch {
			setSummary([]);
			setSlowest([]);
		}
	}, [engine]);

	useEffect(() => {
		if (telemetryOpen) {
			void loadTelemetry();
		}
	}, [telemetryOpen, loadTelemetry]);

	return {
		summary,
		slowest,
		loadTelemetry,
	};
}
