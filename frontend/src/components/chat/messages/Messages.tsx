import { cn } from "@/lib/utils";

const Container = ({ className, ...props }: React.ComponentProps<"div">) => (
  <div
    className={cn("flex flex-col p-2 gap-2 min-h-full", className)}
    {...props}
  />
);

type MessageProps = React.ComponentProps<"div"> & {
  sender: "human" | "ai";
};

const Message = ({ className, sender, ...props }: MessageProps) => (
  <div
    className={cn(
      "max-w-[80%] flex flex-col gap-1",
      sender === "ai" ? "self-start text-left" : "self-end text-right"
    )}
  >
    <div
      className={cn(
        "rounded-lg px-3 py-2",
        sender === "human" && "bg-accent",
        className
      )}
      {...props}
    />
  </div>
);

export const Messages = {
  Container,
  Message,
};
