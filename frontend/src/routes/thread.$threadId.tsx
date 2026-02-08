import { DefaultComposer } from "@/components/chat/composer/DefaultComposer";
import { Messages } from "@/components/chat/messages/Messages";
import { Button } from "@/components/ui/button";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { DB } from "@/lib/db";
import { formatDate } from "@/lib/formatDate";
import { QUERIES } from "@/lib/queries";
import { isFailure } from "@/lib/result";
import { streamToAsyncGenerator } from "@/lib/streamToAsyncGenerator";
import { useMutation, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { EventSourceParserStream } from "eventsource-parser/stream";
import { ArrowLeft, Home, Trash2 } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import Plotly, { type PlotParams } from "react-plotly.js";
import z from "zod";

export const Route = createFileRoute("/thread/$threadId")({
  params: {
    parse: (params) =>
      z.object({ threadId: z.coerce.number().int().positive() }).parse(params),
  },
  loader: async ({ params, context }) => {
    try {
      await context.queryClient.ensureQueryData(
        QUERIES.threads.detail(params.threadId)
      );
    } catch (error) {
      if (typeof error === "string") {
        if (error === "NOT_FOUND") {
          throw notFound();
        }

        throw new Error(error);
      }

      throw error;
    }
  },
  component: RouteComponent,
  notFoundComponent: NotFoundComponent,
});

function RouteComponent() {
  const { threadId } = Route.useParams();
  const { data: thread, refetch } = useSuspenseQuery(
    QUERIES.threads.detail(threadId)
  );

  const examplePrompts = useMemo(
    () => [
      "show layers",
      "how many pubs are flooded?",
      "find 20 dry pubs near metro",
      "recommend 5 safe pubs",
    ],
    []
  );

  const plotContainerRef = useRef<HTMLDivElement | null>(null);
  const [partialMessage, setPartialMessage] = useState<string | null>(null);
  const [plotData, setPlotData] = useState<Pick<PlotParams, "data" | "layout">>(
    () => {
      const firstMessageWithData = thread.messages.find(
        (message) => message.data
      );

      return (
        firstMessageWithData?.data ?? {
          data: [
            {
              type: "scattermapbox",
            },
          ],
          layout: {
            mapbox: {
              // Prague default: we want the first prompt to be immediately meaningful
              // without requiring the user to manually zoom/pan first.
              center: { lat: 50.0755, lon: 14.4378 },
              zoom: 10.5,
              style: "carto-positron",
            },
          },
        }
      );
    }
  );

  const initialCenter = useMemo(() => {
    const center = (plotData.layout as any)?.mapbox?.center;
    if (center && typeof center.lat === "number" && typeof center.lon === "number") {
      return { lat: center.lat as number, lon: center.lon as number };
    }
    return { lat: 50.0755, lon: 14.4378 };
  }, [plotData.layout]);

  const initialZoom = useMemo(() => {
    const zoom = (plotData.layout as any)?.mapbox?.zoom;
    return typeof zoom === "number" ? (zoom as number) : 10.5;
  }, [plotData.layout]);

  const [mapView, setMapView] = useState<{
    center: { lat: number; lon: number };
    zoom: number;
    bbox: { minLon: number; minLat: number; maxLon: number; maxLat: number } | null;
  }>(() => ({
    center: initialCenter,
    zoom: initialZoom,
    bbox: null,
  }));

  const getViewportSize = () => {
    const el = plotContainerRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { width: Math.max(1, Math.floor(r.width)), height: Math.max(1, Math.floor(r.height)) };
  };

  const calcBboxFromCenterZoom = (
    center: { lat: number; lon: number },
    zoom: number,
    viewport: { width: number; height: number }
  ) => {
    // Approximate Mapbox/Plotly viewport bounds using Web Mercator math.
    // This does not need to be perfect: a slightly-larger-than-visible bbox is fine for AOI clipping.
    const R = 6378137;
    const tileSize = 256;
    const lonRad = (center.lon * Math.PI) / 180;
    const latRad = (center.lat * Math.PI) / 180;
    const x = R * lonRad;
    const y = R * Math.log(Math.tan(Math.PI / 4 + latRad / 2));
    const metersPerPixel = (2 * Math.PI * R) / (tileSize * 2 ** zoom);

    const halfW = (viewport.width * metersPerPixel) / 2;
    const halfH = (viewport.height * metersPerPixel) / 2;

    const minX = x - halfW;
    const maxX = x + halfW;
    const minY = y - halfH;
    const maxY = y + halfH;

    const minLon = (minX / R) * (180 / Math.PI);
    const maxLon = (maxX / R) * (180 / Math.PI);
    const minLat = (2 * Math.atan(Math.exp(minY / R)) - Math.PI / 2) * (180 / Math.PI);
    const maxLat = (2 * Math.atan(Math.exp(maxY / R)) - Math.PI / 2) * (180 / Math.PI);

    return {
      minLon,
      minLat,
      maxLon,
      maxLat,
    };
  };

  const getCurrentBbox = () => {
    if (mapView.bbox) return mapView.bbox;
    const viewport = getViewportSize();
    if (!viewport) {
      // Fallback: tiny bbox around center (should only happen during initial render).
      return {
        minLon: mapView.center.lon - 0.05,
        minLat: mapView.center.lat - 0.03,
        maxLon: mapView.center.lon + 0.05,
        maxLat: mapView.center.lat + 0.03,
      };
    }
    return calcBboxFromCenterZoom(mapView.center, mapView.zoom, viewport);
  };

  const { mutate, isPending } = useMutation({
    mutationKey: ["thread", threadId, "create-message"],
    mutationFn: async (text: string) => {
      const createMessageResult = DB.threads.messages.create(threadId, {
        text,
        author: "human",
      });

      if (isFailure(createMessageResult)) {
        throw new Error(createMessageResult.error);
      }

      if (createMessageResult.data.id === 1) {
        DB.threads.updateTitle(threadId, text);
      }

      const { data: threadWithNewHumanMessage } = await refetch();

      const bbox = getCurrentBbox();
      const response = await fetch("http://localhost:8000/invoke", {
        method: "POST",
        body: JSON.stringify({
          ...threadWithNewHumanMessage,
          map: { bbox, view: { center: mapView.center, zoom: mapView.zoom } },
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
            const saveWithData = DB.threads.messages.create(threadId, {
              text: message,
              data,
              author: "ai",
            });
            if (isFailure(saveWithData)) {
              const saveWithoutData = DB.threads.messages.create(threadId, {
                text: message,
                author: "ai",
              });
              if (isFailure(saveWithoutData)) {
                throw new Error(saveWithoutData.error);
              }
            }
            // Important: don't clear the partial message until the thread data refreshes,
            // otherwise the answer can appear to "disappear" briefly (or permanently if refresh fails).
            await refetch();
            message = "";
            data = undefined;
            setPartialMessage(null);
            break;
          }

          case "plot_data": {
            try {
              const plot = JSON.parse(event.data) as Pick<PlotParams, "data" | "layout">;
              // Storing Plotly payload per-message can exceed localStorage quota quickly.
              // Keep it in React state always; persist only if reasonably small.
              const MAX_PERSISTED_PLOT_CHARS = 200_000;
              data = event.data.length <= MAX_PERSISTED_PLOT_CHARS ? plot : undefined;
              setPlotData(plot);
              // Keep mapView in sync with server-provided layout (important when backend recenters/zooms).
              const center = (plot as any)?.layout?.mapbox?.center;
              const zoom = (plot as any)?.layout?.mapbox?.zoom;
              if (
                center &&
                typeof center.lat === "number" &&
                typeof center.lon === "number" &&
                typeof zoom === "number"
              ) {
                const viewport = getViewportSize();
                setMapView({
                  center: { lat: center.lat, lon: center.lon },
                  zoom,
                  bbox: viewport
                    ? calcBboxFromCenterZoom(
                        { lat: center.lat, lon: center.lon },
                        zoom,
                        viewport
                      )
                    : null,
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

  return (
    <div className="grid grid-cols-10 w-full h-screen">
      <div className="col-span-4 h-full border-border border-r">
        <div className="h-full flex flex-col">
          <div className="p-3 flex items-center">
            <div className="mr-2">
              <Button size="icon" asChild variant="ghost">
                <Link to="/">
                  <ArrowLeft />
                </Link>
              </Button>
            </div>
            <h1 className="font-bold grow-1 whitespace-nowrap overflow-ellipsis overflow-hidden">
              {thread.title}
            </h1>
            <div className="mr-2">
              <Button
                size="icon"
                variant="ghost"
                title="Clear messages"
                disabled={isPending || partialMessage !== null}
                onClick={async () => {
                  const result = DB.threads.messages.clear(threadId);
                  if (isFailure(result)) {
                    console.error("ERROR_CLEARING_THREAD_MESSAGES", { result });
                    return;
                  }
                  setPartialMessage(null);
                  await refetch();
                }}
              >
                <Trash2 />
              </Button>
            </div>
            <div className="text-sm text-muted-foreground shrink-0">
              {formatDate(thread.createdAt)}
            </div>
          </div>
          <div className="grow overflow-hidden">
            <ScrollArea>
              <Messages.Container>
                {thread.messages.map((message) => (
                  <Messages.Message key={message.id} sender={message.author}>
                    {message.text}
                  </Messages.Message>
                ))}
                {partialMessage !== null && (
                  <Messages.Message sender="ai">
                    {partialMessage}
                    {" \u2588"}
                  </Messages.Message>
                )}
              </Messages.Container>

              <ScrollBar orientation="vertical" />
            </ScrollArea>
          </div>
          <div className="p-3">
            <div className="mb-2">
              <div className="text-xs text-muted-foreground mb-1">
                Example questions
              </div>
              <div className="flex flex-wrap gap-2">
                {examplePrompts.map((prompt) => (
                  <Button
                    key={prompt}
                    size="sm"
                    variant="secondary"
                    disabled={isPending || partialMessage !== null}
                    onClick={() => mutate(prompt)}
                  >
                    {prompt}
                  </Button>
                ))}
              </div>
            </div>
            <DefaultComposer
              onSubmit={(message) => {
                mutate(message);
              }}
              disabled={isPending || partialMessage !== null}
            />
          </div>
        </div>
      </div>
      <div className="col-span-6 h-full">
        <div
          ref={plotContainerRef}
          className="w-full h-full flex justify-center items-center bg-accent"
        >
          <Plotly
            data={plotData.data}
            layout={{
              ...plotData.layout,
              margin: { l: 0, r: 0, t: 0, b: 0 },
            }}
            config={{ scrollZoom: true, displayModeBar: false }}
            className="w-full h-full overflow-hidden"
            onRelayout={(event) => {
              // Plotly relayout event payload is a shallow object with keys like:
              // - "mapbox.center": {lat, lon}
              // - "mapbox.zoom": number
              const nextCenter =
                (event as any)["mapbox.center"] ??
                ((typeof (event as any)["mapbox.center.lat"] === "number" &&
                  typeof (event as any)["mapbox.center.lon"] === "number" &&
                  {
                    lat: (event as any)["mapbox.center.lat"],
                    lon: (event as any)["mapbox.center.lon"],
                  }) ||
                  null);
              const nextZoom = (event as any)["mapbox.zoom"];

              setMapView((prev) => {
                const center =
                  nextCenter &&
                  typeof nextCenter.lat === "number" &&
                  typeof nextCenter.lon === "number"
                    ? { lat: nextCenter.lat as number, lon: nextCenter.lon as number }
                    : prev.center;
                const zoom = typeof nextZoom === "number" ? (nextZoom as number) : prev.zoom;
                const viewport = getViewportSize();
                const bbox = viewport ? calcBboxFromCenterZoom(center, zoom, viewport) : prev.bbox;
                return { center, zoom, bbox };
              });
            }}
          />
        </div>
      </div>
    </div>
  );
}

function NotFoundComponent() {
  const { threadId } = Route.useParams();

  return (
    <div className="min-h-screen flex flex-col gap-4 items-center justify-center bg-accent">
      <h1 className="font-bold text-3xl">Thread not found</h1>
      <div className="border border-border rounded-lg max-w-full bg-background p-4">
        Unfortunately we weren't able to find thread with ID: {threadId}
      </div>
      <div>
        <Button asChild size="lg" className="font-bold">
          <Link to="/">
            Go home
            <Home className="size-5" />
          </Link>
        </Button>
      </div>
    </div>
  );
}
