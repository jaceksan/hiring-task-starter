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
import { ArrowLeft, Home } from "lucide-react";
import { useState } from "react";
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
              center: { lat: 20, lon: 0 },
              zoom: 2,
              style: "carto-positron",
            },
          },
        }
      );
    }
  );

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

      const response = await fetch("http://localhost:8000/invoke", {
        method: "POST",
        body: JSON.stringify(threadWithNewHumanMessage),
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
      let data = undefined;
      setPartialMessage(message);

      for await (const event of generator) {
        switch (event.event) {
          case "append": {
            message += " " + event.data;
            setPartialMessage(message);
            break;
          }

          case "commit": {
            message += event.data;
            DB.threads.messages.create(threadId, {
              text: message,
              data,
              author: "ai",
            });
            refetch();
            message = "";
            data = undefined;
            setPartialMessage(message);
            break;
          }

          case "plot_data": {
            try {
              data = JSON.parse(event.data);
              setPlotData(data);
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
        <div className="w-full h-full flex justify-center items-center bg-accent">
          <Plotly
            data={plotData.data}
            layout={{
              ...plotData.layout,
              margin: { l: 0, r: 0, t: 0, b: 0 },
            }}
            config={{ scrollZoom: true, displayModeBar: false }}
            className="w-full h-full overflow-hidden"
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
