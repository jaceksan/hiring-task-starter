import { ArrowUp } from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import {
	createContext,
	useContext,
	useEffectEvent,
	useMemo,
	useState,
} from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ComposerContext = createContext<{
	onSubmit: () => void;
	message: string;
	setMessage: Dispatch<SetStateAction<string>>;
	disabled?: boolean;
} | null>(null);

const Provider = (props: {
	children: ReactNode;
	onSubmit?: (message: string) => void;
	disabled?: boolean;
}) => {
	const [message, setMessage] = useState("");

	const onSubmit = useEffectEvent(() => {
		const trimmed = message.trim();
		if (trimmed) {
			props.onSubmit?.(trimmed);
			setMessage("");
		}
	});

	const model = useMemo(
		() => ({
			message,
			setMessage,
			onSubmit,
			disabled: props.disabled,
		}),
		[message, onSubmit, props.disabled],
	);

	return (
		<ComposerContext.Provider value={model}>
			<form
				onSubmit={(event) => {
					event.preventDefault();
					onSubmit();
				}}
			>
				{props.children}
			</form>
		</ComposerContext.Provider>
	);
};

const useComposerContext = () => {
	const value = useContext(ComposerContext);

	if (!value) {
		throw new Error(
			"useComposerContext can only be used inside ComposerContext.Provider",
		);
	}

	return value;
};

const Container = ({ className, ...props }: React.ComponentProps<"div">) => {
	return (
		<div
			className={cn(
				"p-1 border border-border rounded-2xl flex flex-col gap-1",
				className,
			)}
			{...props}
		/>
	);
};

const Textarea = ({
	className,
	...props
}: Omit<
	React.ComponentProps<"textarea">,
	"onInput" | "placeholder" | "disabled"
>) => {
	const { message, setMessage, disabled, onSubmit } = useComposerContext();

	return (
		<textarea
			placeholder="Ask PangeAI..."
			className={cn("p-2 resize-none focus:outline-none", className)}
			onKeyDown={(event) => {
				if (event.key === "Enter" && event.shiftKey === false) {
					event.preventDefault();
					event.stopPropagation();
					onSubmit();
				}
			}}
			onInput={(event) => {
				const textarea = event.currentTarget;
				textarea.style.height = "auto"; // reset height
				textarea.style.height = `${textarea.scrollHeight}px`; // adjust height
				setMessage(event.currentTarget.value);
			}}
			value={message}
			disabled={disabled}
			{...props}
		/>
	);
};

const Toolbar = ({ className, ...props }: React.ComponentProps<"div">) => {
	return (
		<div
			className={cn("flex justify-between items-center", className)}
			{...props}
		/>
	);
};

const ToolbarButtons = ({
	className,
	...props
}: React.ComponentProps<"div">) => {
	return <div className={cn("flex items-center", className)} {...props} />;
};

const SendButton = () => {
	const { disabled } = useComposerContext();

	return (
		<Button
			size="icon"
			variant="default"
			className="rounded-full"
			type="submit"
			disabled={disabled}
		>
			<ArrowUp />
		</Button>
	);
};

export const Composer = {
	Provider,
	Container,
	Textarea,
	Toolbar,
	ToolbarLeft: ToolbarButtons,
	ToolbarRight: ToolbarButtons,
	SendButton,
};
