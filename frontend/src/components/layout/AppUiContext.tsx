import { createContext, useContext, useEffect, useMemo, useState } from "react";

type Engine = "in_memory" | "duckdb";

type AppUiState = {
	scenarioId: string;
	setScenarioId: (id: string) => void;
	engine: Engine;
	setEngine: (e: Engine) => void;
	telemetryOpen: boolean;
	setTelemetryOpen: (v: boolean) => void;
	autoMinimizeChat: boolean;
	setAutoMinimizeChat: (v: boolean) => void;
};

const Ctx = createContext<AppUiState | null>(null);

export function AppUiProvider(props: { children: React.ReactNode }) {
	const [scenarioId, setScenarioId] = useState<string>(() => {
		const v = window.localStorage.getItem("pange_scenario");
		return v?.trim() ? v : "prague_transport";
	});

	useEffect(() => {
		window.localStorage.setItem("pange_scenario", scenarioId);
	}, [scenarioId]);

	const [engine, setEngine] = useState<Engine>(() => {
		const v = window.localStorage.getItem("pange_engine");
		return v === "duckdb" ? "duckdb" : "in_memory";
	});

	useEffect(() => {
		window.localStorage.setItem("pange_engine", engine);
	}, [engine]);

	const [telemetryOpen, setTelemetryOpen] = useState(false);

	const [autoMinimizeChat, setAutoMinimizeChat] = useState<boolean>(() => {
		const raw = window.localStorage.getItem("pange_auto_minimize_chat");
		// Default: enabled (map-first behavior).
		if (raw === null) return true;
		return raw === "1" || raw === "true";
	});

	useEffect(() => {
		window.localStorage.setItem(
			"pange_auto_minimize_chat",
			autoMinimizeChat ? "1" : "0",
		);
	}, [autoMinimizeChat]);

	const value = useMemo<AppUiState>(
		() => ({
			scenarioId,
			setScenarioId,
			engine,
			setEngine,
			telemetryOpen,
			setTelemetryOpen,
			autoMinimizeChat,
			setAutoMinimizeChat,
		}),
		[scenarioId, engine, telemetryOpen, autoMinimizeChat],
	);

	return <Ctx.Provider value={value}>{props.children}</Ctx.Provider>;
}

export function useAppUi() {
	const v = useContext(Ctx);
	if (!v) throw new Error("useAppUi must be used within AppUiProvider");
	return v;
}
