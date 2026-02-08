import { createFileRoute } from "@tanstack/react-router";
import Plotly from "react-plotly.js";
import { useAppUi } from "@/components/layout/AppUiContext";
import { useEffect, useState } from "react";

export const Route = createFileRoute("/")({
  component: App,
});

function App() {
  const { scenarioId } = useAppUi();
  const [view, setView] = useState<{ lat: number; lon: number; zoom: number }>({
    lat: 50.0755,
    lon: 14.4378,
    zoom: 10.5,
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch("http://localhost:8000/scenarios");
        if (!resp.ok) return;
        const list = (await resp.json()) as any[];
        const match = Array.isArray(list) ? list.find((s) => s?.id === scenarioId) : null;
        const dv = match?.defaultView;
        const c = dv?.center;
        const z = dv?.zoom;
        if (
          c &&
          typeof c.lat === "number" &&
          typeof c.lon === "number" &&
          typeof z === "number" &&
          !cancelled
        ) {
          setView({ lat: c.lat as number, lon: c.lon as number, zoom: z as number });
        }
      } catch {
        // ignore
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scenarioId]);

  return (
    <div className="w-full h-full bg-accent relative">
      <Plotly
        data={[
          {
            type: "scattermapbox",
          },
        ]}
        layout={{
          mapbox: {
            center: { lat: view.lat, lon: view.lon },
            zoom: view.zoom,
            style: "carto-positron",
          },
          showlegend: false,
          margin: { l: 0, r: 0, t: 0, b: 0 },
        }}
        config={{ scrollZoom: true, displayModeBar: false }}
        useResizeHandler={true}
        style={{ width: "100%", height: "100%" }}
        className="w-full h-full overflow-hidden"
      />
      <div className="absolute top-3 left-3 z-10 rounded-md border border-border bg-background/90 px-3 py-2 text-sm max-w-[420px]">
        <div className="font-semibold mb-1">Map-first view</div>
        <div className="text-muted-foreground">
          Pick a thread in the left sidebar (or create a new one) to start chatting.
        </div>
      </div>
    </div>
  );
}
