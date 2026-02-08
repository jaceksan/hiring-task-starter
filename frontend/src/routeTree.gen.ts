/* eslint-disable */

// @ts-nocheck

// This file is intentionally kept as a small, explicit route tree + typing shim.
// We do NOT use the TanStack file-based router generator anymore (to avoid `$` in filenames),
// but we still want the strongly-typed `Link to="/thread/$threadId"` API shape.

import { Route as rootRouteImport } from "./routes/__root";
import { Route as IndexRouteImport } from "./routes/index";
import { Route as ThreadThreadIdRouteImport } from "./routes/thread/threadId";

const IndexRoute = IndexRouteImport.update({
	id: "/",
	path: "/",
	getParentRoute: () => rootRouteImport,
} as any);

const ThreadThreadIdRoute = ThreadThreadIdRouteImport.update({
	id: "/thread/$threadId",
	path: "/thread/$threadId",
	getParentRoute: () => rootRouteImport,
} as any);

export interface FileRoutesByFullPath {
	"/": typeof IndexRoute;
	"/thread/$threadId": typeof ThreadThreadIdRoute;
}
export interface FileRoutesByTo {
	"/": typeof IndexRoute;
	"/thread/$threadId": typeof ThreadThreadIdRoute;
}
export interface FileRoutesById {
	__root__: typeof rootRouteImport;
	"/": typeof IndexRoute;
	"/thread/$threadId": typeof ThreadThreadIdRoute;
}
export interface FileRouteTypes {
	fileRoutesByFullPath: FileRoutesByFullPath;
	fullPaths: "/" | "/thread/$threadId";
	fileRoutesByTo: FileRoutesByTo;
	to: "/" | "/thread/$threadId";
	id: "__root__" | "/" | "/thread/$threadId";
	fileRoutesById: FileRoutesById;
}
export interface RootRouteChildren {
	IndexRoute: typeof IndexRoute;
	ThreadThreadIdRoute: typeof ThreadThreadIdRoute;
}

declare module "@tanstack/react-router" {
	interface FileRoutesByPath {
		"/": {
			id: "/";
			path: "/";
			fullPath: "/";
			preLoaderRoute: typeof IndexRouteImport;
			parentRoute: typeof rootRouteImport;
		};
		"/thread/$threadId": {
			id: "/thread/$threadId";
			path: "/thread/$threadId";
			fullPath: "/thread/$threadId";
			preLoaderRoute: typeof ThreadThreadIdRouteImport;
			parentRoute: typeof rootRouteImport;
		};
	}
}

const rootRouteChildren: RootRouteChildren = {
	IndexRoute,
	ThreadThreadIdRoute,
};

export const routeTree = rootRouteImport
	._addFileChildren(rootRouteChildren)
	._addFileTypes<FileRouteTypes>();

