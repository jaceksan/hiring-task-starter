import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { SpoolIcon } from "lucide-react";
import { useAppUi } from "@/components/layout/AppUiContext";
import { DB } from "@/lib/db";
import { QUERIES } from "@/lib/queries";
import { isFailure } from "@/lib/result";
import { sleep } from "@/lib/sleep";
import { Button } from "../ui/button";

export const NewThreadButton = () => {
	const navigate = useNavigate();
	const { scenarioId } = useAppUi();

	const queryClient = useQueryClient();

	const { mutate, isPending } = useMutation({
		mutationKey: ["thread-create", scenarioId],
		mutationFn: async () => {
			await sleep(300);

			const result = DB.threads.create(scenarioId, { title: "New thread" });

			if (isFailure(result)) {
				throw result.error;
			}

			return result.data;
		},
		onError: (error) => {
			alert(`${error.name}: ${error.message}`);
		},
		onSuccess: (thread) => {
			queryClient.invalidateQueries({
				queryKey: QUERIES.threads.list(scenarioId).queryKey,
			});

			navigate({ to: "/thread/$threadId", params: { threadId: thread.id } });
		},
	});

	return (
		<Button
			onClick={() => mutate()}
			disabled={isPending}
			size="lg"
			className="font-bold"
		>
			<SpoolIcon />
			Start new thread
		</Button>
	);
};
