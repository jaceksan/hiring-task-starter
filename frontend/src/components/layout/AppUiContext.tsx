import { createContext, useContext, useEffect, useMemo, useState } from "react";

type Engine = "in_memory" | "duckdb";

type AppUiState = {
  engine: Engine;
  setEngine: (e: Engine) => void;
  telemetryOpen: boolean;
  setTelemetryOpen: (v: boolean) => void;
  autoMinimizeChat: boolean;
  setAutoMinimizeChat: (v: boolean) => void;
};

const Ctx = createContext<AppUiState | null>(null);

export function AppUiProvider(props: { children: React.ReactNode }) {
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
      autoMinimizeChat ? "1" : "0"
    );
  }, [autoMinimizeChat]);

  const value = useMemo<AppUiState>(
    () => ({
      engine,
      setEngine,
      telemetryOpen,
      setTelemetryOpen,
      autoMinimizeChat,
      setAutoMinimizeChat,
    }),
    [engine, telemetryOpen, autoMinimizeChat]
  );

  return <Ctx.Provider value={value}>{props.children}</Ctx.Provider>;
}

export function useAppUi() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAppUi must be used within AppUiProvider");
  return v;
}

