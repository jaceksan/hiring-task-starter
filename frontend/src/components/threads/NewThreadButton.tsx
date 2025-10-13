import { DB } from "@/lib/db";
import { isFailure } from "@/lib/result";
import { sleep } from "@/lib/sleep";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "../ui/button";
import { useNavigate } from "@tanstack/react-router";
import { SpoolIcon } from "lucide-react";
import { QUERIES } from "@/lib/queries";

export const NewThreadButton = () => {
  const navigate = useNavigate();

  const queryClient = useQueryClient();

  const { mutate, isPending } = useMutation({
    mutationKey: ["thread-create"],
    mutationFn: async () => {
      await sleep(300);

      const result = DB.threads.create({ title: "New thread" });

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
        queryKey: QUERIES.threads.list.queryKey,
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
