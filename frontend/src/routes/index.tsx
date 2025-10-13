import { NewThreadButton } from "@/components/threads/NewThreadButton";
import { ThreadsList } from "@/components/threads/ThreadsList";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: App,
});

function App() {
  return (
    <div className="min-h-screen flex flex-col gap-4 items-center justify-center bg-accent">
      <div className="border border-border rounded-lg w-[400px] max-w-full p-1 bg-background">
        <ThreadsList />
      </div>
      <div>
        <NewThreadButton />
      </div>
    </div>
  );
}
