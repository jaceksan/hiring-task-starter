export type Success<D> = { type: "success"; data: D };

export type Failure<E> = { type: "failure"; error: E };

export type Result<D, E> = Success<D> | Failure<E>;

export const success = <D>(data: D): Success<D> => ({
	type: "success",
	data,
});

export const failure = <E>(error: E): Failure<E> => ({
	type: "failure",
	error,
});

export const isSuccess = <D, E>(result: Result<D, E>): result is Success<D> =>
	result.type === "success";

export const isFailure = <D, E>(result: Result<D, E>): result is Failure<E> =>
	result.type === "failure";

export const tryTo = <Data>(fn: () => Data) => {
	try {
		const result = fn();
		return success(result);
	} catch (error) {
		return failure(error);
	}
};
