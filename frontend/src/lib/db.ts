import { z } from "zod";
import { LS } from "./localStorage";
import { isFailure, isSuccess, success } from "./result";

/// SCHEMAS

const threadSchema = z.object({
	id: z.number().int().positive(),
	createdAt: z.iso.datetime(),
	title: z.string(),
});

const threadsMetaSchema = z.array(threadSchema);

const messageSchema = z.object({
	id: z.number().int().positive(),
	createdAt: z.iso.datetime(),
	author: z.enum(["human", "ai"]),
	text: z.string(),
	data: z.any().optional(),
});

const threadDetailSchema = threadSchema.and(
	z.object({
		messages: z.array(messageSchema),
	}),
);

/// APIs

const LS_PREFIX = "htsapp_";

const LS_KEYS = {
	threads: {
		list: `${LS_PREFIX}threads_list`,
		detail: (id: number) => `${LS_PREFIX}thread-${id}`,
	},
};

const listThreads = () => {
	const result = LS.getItem(LS_KEYS.threads.list, threadsMetaSchema);

	if (isFailure(result)) {
		if (result.error === "NOT_FOUND") {
			return success([]);
		}
	}

	return result;
};

const getThread = (id: number) =>
	LS.getItem(LS_KEYS.threads.detail(id), threadDetailSchema);

const saveThreadDetail = (thread: z.input<typeof threadDetailSchema>) =>
	LS.setItem(LS_KEYS.threads.detail(thread.id), thread);

const createThread = (
	data: Omit<z.input<typeof threadSchema>, "id" | "createdAt">,
) => {
	const listResult = listThreads();

	const list = isSuccess(listResult) ? listResult.data : [];

	const newThread = {
		id: list.length + 1,
		createdAt: new Date().toISOString(),
		...data,
	};

	list.push(newThread);

	const saveListResult = LS.setItem(LS_KEYS.threads.list, list);

	if (isFailure(saveListResult)) {
		return saveListResult;
	}

	const saveDetailResult = saveThreadDetail({ ...newThread, messages: [] });

	if (isFailure(saveDetailResult)) {
		return saveDetailResult;
	}

	return success(newThread);
};

const updateThreadTitle = (threadId: number, title: string) => {
	const getThreadResult = getThread(threadId);

	if (isFailure(getThreadResult)) {
		return getThreadResult;
	}

	const thread = getThreadResult.data;

	thread.title = title;

	const saveThreadResult = saveThreadDetail(thread);

	if (isFailure(saveThreadResult)) {
		return saveThreadResult;
	}

	const getListResult = listThreads();

	if (isFailure(getListResult)) {
		return getListResult;
	}

	const list = getListResult.data;

	for (const thread of list) {
		if (thread.id === threadId) {
			thread.title = title;
		}
	}

	const saveListResult = LS.setItem(LS_KEYS.threads.list, list);

	if (isFailure(saveListResult)) {
		return saveListResult;
	}

	return success(void 0);
};

const createThreadMessage = (
	threadId: number,
	message: Omit<z.infer<typeof messageSchema>, "id" | "createdAt">,
) => {
	const getResult = getThread(threadId);

	if (isFailure(getResult)) {
		return getResult;
	}

	const thread = getResult.data;

	const newMessage = {
		id: thread.messages.length + 1,
		createdAt: new Date().toISOString(),
		...message,
	};

	thread.messages.push(newMessage);

	const saveDetailResult = saveThreadDetail(thread);

	if (isFailure(saveDetailResult)) {
		return saveDetailResult;
	}

	return success(newMessage);
};

const clearThreadMessages = (threadId: number) => {
	const getResult = getThread(threadId);

	if (isFailure(getResult)) {
		return getResult;
	}

	const thread = getResult.data;
	thread.messages = [];

	const saveDetailResult = saveThreadDetail(thread);
	if (isFailure(saveDetailResult)) {
		return saveDetailResult;
	}

	return success(void 0);
};

/// DB

export const DB = {
	threads: {
		create: createThread,
		list: listThreads,
		get: getThread,
		updateTitle: updateThreadTitle,
		messages: {
			create: createThreadMessage,
			clear: clearThreadMessages,
		},
	},
};
