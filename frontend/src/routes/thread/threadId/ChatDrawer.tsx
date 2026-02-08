import { Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { DefaultComposer } from "@/components/chat/composer/DefaultComposer";
import { Messages } from "@/components/chat/messages/Messages";
import { Button } from "@/components/ui/button";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { formatDate } from "@/lib/formatDate";

export function ChatDrawer(props: {
	open: boolean;
	setOpen: (open: boolean) => void;
	threadTitle: string;
	threadCreatedAt: string;
	messages: { id: number; author: "human" | "ai"; text: string }[];
	examplePrompts: string[];
	partialMessage: string | null;
	disabled: boolean;
	onClearMessages: () => Promise<void> | void;
	onSubmit: (message: string) => void;
	onPromptClick: (prompt: string) => void;
}) {
	const {
		open,
		setOpen,
		threadTitle,
		threadCreatedAt,
		messages,
		examplePrompts,
		partialMessage,
		disabled,
		onClearMessages,
		onSubmit,
		onPromptClick,
	} = props;

	const messagesScrollRootRef = useRef<HTMLDivElement | null>(null);

	const scrollMessagesToBottom = useCallback((behavior: ScrollBehavior) => {
		const root = messagesScrollRootRef.current;
		if (!root) return;
		const viewport = root.querySelector<HTMLElement>(
			'[data-slot="scroll-area-viewport"]',
		);
		if (!viewport) return;
		viewport.scrollTo({ top: viewport.scrollHeight, behavior });
	}, []);

	// When opening the drawer (or after reload), jump to the latest message.
	useEffect(() => {
		if (!open) return;
		// Let layout settle first (Plotly resize + drawer transition).
		const id = window.setTimeout(() => scrollMessagesToBottom("auto"), 0);
		return () => window.clearTimeout(id);
	}, [open, scrollMessagesToBottom]);

	// When new messages arrive while drawer is open, follow the conversation.
	useEffect(() => {
		if (!open) return;
		// Re-run on new messages / streaming changes.
		void messages.length;
		void partialMessage;
		scrollMessagesToBottom("smooth");
	}, [open, messages.length, partialMessage, scrollMessagesToBottom]);

	const lastAiText = useMemo(() => {
		for (let i = messages.length - 1; i >= 0; i--) {
			if (messages[i]?.author === "ai") return (messages[i]?.text ?? "").trim();
		}
		return "";
	}, [messages]);

	const lastAiPreview = useMemo(() => {
		const t = lastAiText.replace(/\s+/g, " ").trim();
		if (!t) return "";
		return t.length > 140 ? `${t.slice(0, 140)}…` : t;
	}, [lastAiText]);

	return (
		<div
			className={[
				"absolute left-0 right-0 bottom-0 z-20",
				"border-t border-border bg-background/95 backdrop-blur",
				open ? "h-[42vh]" : "h-[60px]",
			].join(" ")}
		>
			<div className="h-full flex flex-col min-h-0">
				<div className="h-[60px] shrink-0 px-3 flex items-center gap-2 border-b border-border">
					<Button
						size="sm"
						variant="secondary"
						onClick={() => setOpen(!open)}
						title={open ? "Collapse chat" : "Expand chat"}
					>
						{open ? "Collapse" : "Chat"}
					</Button>

					<div className="font-semibold whitespace-nowrap overflow-hidden overflow-ellipsis">
						{threadTitle}
					</div>

					{!open && lastAiPreview && (
						<div className="text-xs text-muted-foreground whitespace-nowrap overflow-hidden overflow-ellipsis">
							{lastAiPreview}
						</div>
					)}

					<div className="ml-auto flex items-center gap-1">
						<Button
							size="icon"
							variant="ghost"
							title="Clear messages"
							disabled={disabled}
							onClick={() => void onClearMessages()}
						>
							<Trash2 />
						</Button>
						<div className="text-xs text-muted-foreground shrink-0 ml-1">
							{formatDate(threadCreatedAt)}
						</div>
					</div>
				</div>

				{open && (
					<>
						<div className="flex-1 min-h-0 overflow-hidden">
							<div ref={messagesScrollRootRef} className="h-full">
								<ScrollArea className="h-full">
									<Messages.Container>
										{messages.map((message) => (
											<Messages.Message
												key={message.id}
												sender={message.author}
											>
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
						</div>

						<div className="p-3 border-t border-border">
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
											disabled={disabled}
											onClick={() => onPromptClick(prompt)}
										>
											{prompt}
										</Button>
									))}
								</div>
							</div>
							<DefaultComposer onSubmit={onSubmit} disabled={disabled} />
						</div>
					</>
				)}
			</div>
		</div>
	);
}
