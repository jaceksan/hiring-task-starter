import { createFileRoute } from "@tanstack/react-router";
import Plotly from "react-plotly.js";

export const Route = createFileRoute("/")({
  component: App,
});

function App() {
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
            center: { lat: 50.0755, lon: 14.4378 },
            zoom: 10.5,
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
