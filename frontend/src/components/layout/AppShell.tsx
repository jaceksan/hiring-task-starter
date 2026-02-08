import { NewThreadButton } from "@/components/threads/NewThreadButton";
import { ThreadsList } from "@/components/threads/ThreadsList";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { AppUiProvider } from "@/components/layout/AppUiContext";
import { TopBar } from "@/components/layout/TopBar";

export function AppShell(props: { topBar?: React.ReactNode; children: React.ReactNode }) {
  return (
    <AppUiProvider>
      <div className="h-screen w-screen flex bg-background text-foreground">
        <aside className="w-[320px] shrink-0 border-r border-border bg-background">
          <div className="h-full flex flex-col min-h-0">
            <div className="p-3 border-b border-border">
              <div className="font-semibold">Threads</div>
            </div>

            <div className="flex-1 min-h-0">
              <ScrollArea className="h-full">
                <div className="p-2">
                  <ThreadsList />
                </div>
                <ScrollBar orientation="vertical" />
              </ScrollArea>
            </div>

            <div className="p-3 border-t border-border">
              <NewThreadButton />
            </div>
          </div>
        </aside>

        <div className="flex-1 min-w-0 flex flex-col">
          <div className="h-12 shrink-0 border-b border-border flex items-center px-3 bg-background/95 backdrop-blur">
            {props.topBar ?? <TopBar />}
          </div>
          <main className="flex-1 min-h-0 relative">{props.children}</main>
        </div>
      </div>
    </AppUiProvider>
  );
}

