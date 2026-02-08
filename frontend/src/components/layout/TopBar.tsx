import { BarChart3 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAppUi } from "@/components/layout/AppUiContext";
import { Button } from "@/components/ui/button";

type ScenarioDefaultView = {
	center?: { lat: number; lon: number };
	zoom?: number;
} | null;

type Scenario = {
	id: string;
	title: string;
	defaultView: ScenarioDefaultView;
	dataSize?: string;
	hasGeoParquet?: boolean;
	enabled?: boolean;
};

export function TopBar() {
	const {
		scenarioId,
		setScenarioId,
		engine,
		setEngine,
		telemetryOpen,
		setTelemetryOpen,
		autoMinimizeChat,
		setAutoMinimizeChat,
	} = useAppUi();

	const [scenarios, setScenarios] = useState<Scenario[]>([]);

	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				const resp = await fetch("http://localhost:8000/scenarios");
				if (!resp.ok) return;
				const raw = (await resp.json()) as unknown;
				const data = Array.isArray(raw) ? (raw as Scenario[]) : [];
				if (!cancelled) setScenarios(data);
			} catch {
				// ignore
			}
		})();
		return () => {
			cancelled = true;
		};
	}, []);

	const scenarioOptions = useMemo(() => {
		if (scenarios.length > 0) return scenarios;
		return [
			{
				id: "prague_transport",
				title: "Prague Flood & Transport",
				defaultView: null,
				dataSize: "small",
				hasGeoParquet: false,
				enabled: true,
			},
		];
	}, [scenarios]);

	const selectedScenario = useMemo(() => {
		return (
			scenarioOptions.find((s) => s.id === scenarioId) ??
			scenarioOptions[0] ??
			null
		);
	}, [scenarioOptions, scenarioId]);

	const isLargeScenario =
		(selectedScenario?.dataSize ?? "small").toLowerCase() === "large";
	const requiresDuckdb =
		isLargeScenario || Boolean(selectedScenario?.hasGeoParquet);

	useEffect(() => {
		if (requiresDuckdb && engine !== "duckdb") {
			setEngine("duckdb");
		}
	}, [requiresDuckdb, engine, setEngine]);

	return (
		<div className="w-full flex items-center gap-3">
			<div className="flex items-center gap-2">
				<div className="text-xs text-muted-foreground">Scenario</div>
				<select
					className="h-8 rounded-md border border-border bg-background px-2 text-sm max-w-[260px]"
					value={scenarioId}
					onChange={(e) => setScenarioId(e.target.value)}
					title="Select scenario pack"
				>
					{scenarioOptions.map((s) => (
						<option
							key={s.id}
							value={s.id}
							disabled={s.enabled === false}
							title={s.enabled === false ? "Not enabled yet" : undefined}
						>
							{s.title}
						</option>
					))}
				</select>
			</div>

			<div className="flex items-center gap-2">
				<div className="text-xs text-muted-foreground">Engine</div>
				<select
					className="h-8 rounded-md border border-border bg-background px-2 text-sm"
					value={engine}
					onChange={(e) =>
						setEngine(e.target.value === "duckdb" ? "duckdb" : "in_memory")
					}
					title="Select backend engine"
				>
					<option value="in_memory" disabled={requiresDuckdb}>
						In-memory{requiresDuckdb ? " (disabled for this scenario)" : ""}
					</option>
					<option value="duckdb">DuckDB</option>
				</select>
			</div>

			<div className="flex items-center gap-1">
				<Button
					size="sm"
					variant="ghost"
					title="Reset telemetry DB"
					onClick={async () => {
						try {
							await fetch("http://localhost:8000/telemetry/reset", {
								method: "POST",
							});
						} catch {
							// ignore
						}
					}}
				>
					Reset telemetry
				</Button>
				<Button
					size="sm"
					variant={telemetryOpen ? "secondary" : "ghost"}
					title="Open telemetry summary"
					onClick={() => setTelemetryOpen(!telemetryOpen)}
				>
					<BarChart3 className="mr-1 size-4" />
					Telemetry
				</Button>
			</div>

			<label className="flex items-center gap-2 text-xs text-muted-foreground select-none">
				<input
					type="checkbox"
					className="accent-primary"
					checked={autoMinimizeChat}
					onChange={(e) => setAutoMinimizeChat(e.target.checked)}
					title="Auto-minimize chat after answer commits"
				/>
				Auto-minimize chat
			</label>

			<div className="ml-auto text-sm text-muted-foreground truncate">
				Map-first view
			</div>
		</div>
	);
}
