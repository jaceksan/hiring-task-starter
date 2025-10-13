import { queryOptions } from "@tanstack/react-query";
import { sleep } from "./sleep";
import { DB } from "./db";
import { isFailure } from "./result";

const threadsListQueryOptions = queryOptions({
  queryKey: ["threads-list"],
  queryFn: async () => {
    await sleep(300);

    const result = DB.threads.list();

    if (isFailure(result)) {
      throw result.error;
    }

    return result.data;
  },
});

const threadDetailQueryOptions = (id: number) =>
  queryOptions({
    queryKey: ["thread-detail", id],
    queryFn: async () => {
      const result = DB.threads.get(id);

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
