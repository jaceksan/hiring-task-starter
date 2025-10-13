import { failure, isFailure, success, tryTo } from "./result";
import { z, ZodType } from "zod";

/// HELPERS

const lsGetItem = <Schema extends ZodType>(key: string, schema: Schema) => {
  const lsResult = tryTo(() => localStorage.getItem(key));

  if (isFailure(lsResult)) {
    return failure("ACCESS_BLOCKED" as const);
  }

  const rawData = lsResult.data;

  if (!rawData) {
    return failure("NOT_FOUND" as const);
  }

  const jsonParseResult = tryTo(() => JSON.parse(rawData));

  if (isFailure(jsonParseResult)) {
    return failure("INVALID_JSON" as const);
  }

  const schemaParseResult = schema.safeParse(jsonParseResult.data);

  if (!schemaParseResult.success) {
    return failure("INVALID_DATA" as const);
  }

  return success(schemaParseResult.data);
};

const lsSetItem = <Schema extends ZodType>(
  key: string,
  data: z.Infer<Schema>
) => {
  const stringifyResult = tryTo(() => JSON.stringify(data));

  if (isFailure(stringifyResult)) {
    return failure("STRINGIFY_ERROR" as const);
  }

  const lsResult = tryTo(() => localStorage.setItem(key, stringifyResult.data));

  if (isFailure(lsResult)) {
    return failure("ACCESS_BLOCKED" as const);
  }

  return success(void 0);
};

export const LS = {
  getItem: lsGetItem,
  setItem: lsSetItem,
};
