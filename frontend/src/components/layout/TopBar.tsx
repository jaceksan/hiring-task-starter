import { Button } from "@/components/ui/button";
import { useAppUi } from "@/components/layout/AppUiContext";
import { BarChart3 } from "lucide-react";

export function TopBar() {
  const {
    engine,
    setEngine,
    telemetryOpen,
    setTelemetryOpen,
    autoMinimizeChat,
    setAutoMinimizeChat,
  } = useAppUi();

  return (
    <div className="w-full flex items-center gap-3">
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
          <option value="in_memory">In-memory</option>
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
              await fetch("http://localhost:8000/telemetry/reset", { method: "POST" });
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

