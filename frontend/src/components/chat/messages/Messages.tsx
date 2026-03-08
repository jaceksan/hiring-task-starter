import { cn } from "@/lib/utils";

const Container = ({ className, ...props }: React.ComponentProps<"div">) => (
	<div
		className={cn("flex flex-col p-1 gap-0.5 min-h-full text-[13px]", className)}
		{...props}
	/>
);

type MessageProps = React.ComponentProps<"div"> & {
	sender: "human" | "ai";
};

const Message = ({ className, sender, ...props }: MessageProps) => (
	<div
		className={cn(
			"max-w-[92%] flex flex-col gap-0.5",
			sender === "ai" ? "self-start text-left" : "self-end text-right",
		)}
	>
		<div
			className={cn(
				"rounded-md px-2.5 py-1.5 leading-snug",
				sender === "human" && "bg-accent",
				className,
			)}
			{...props}
		/>
	</div>
);

export const Messages = {
	Container,
	Message,
};
