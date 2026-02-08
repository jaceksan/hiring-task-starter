import { queryOptions } from "@tanstack/react-query";
import { DB } from "./db";
import { isFailure } from "./result";
import { sleep } from "./sleep";

const threadsListQueryOptions = (scenarioId: string) =>
	queryOptions({
		queryKey: ["threads-list", scenarioId],
		queryFn: async () => {
			await sleep(300);

			const result = DB.threads.list(scenarioId);

			if (isFailure(result)) {
				throw result.error;
			}

			return result.data;
		},
	});

const threadDetailQueryOptions = (scenarioId: string, id: number) =>
	queryOptions({
		queryKey: ["thread-detail", scenarioId, id],
		queryFn: async () => {
			const result = DB.threads.get(scenarioId, id);

			if (isFailure(result)) {
				throw result.error;
			}

			return result.data;
		},
	});

export const QUERIES = {
	threads: {
		list: threadsListQueryOptions,
		detail: threadDetailQueryOptions,
	},
};
