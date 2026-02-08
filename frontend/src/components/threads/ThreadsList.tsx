import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { formatDate } from "@/lib/formatDate";
import { QUERIES } from "@/lib/queries";
import { Button } from "../ui/button";
import { Skeleton } from "../ui/skeleton";

export const ThreadsList = () => {
	const { isSuccess, data, isError, error, isLoading } = useQuery(
		QUERIES.threads.list,
	);

	if (isLoading) {
		return (
			<div className="flex flex-col gap-2">
				<Skeleton className="w-full h-14" />
				<Skeleton className="w-full h-14" />
				<Skeleton className="w-full h-14" />
			</div>
		);
	}

	if (isError) {
		return (
			<div className="p-4 bg-red-200 text-red-800 font-bold rounded-lg">
				{error.message}
			</div>
		);
	}

	if (isSuccess && data.length) {
		return (
			<ul className="flex flex-col">
				{data.map((thread) => (
					<li key={thread.id}>
						<Button asChild className="flex h-auto w-full" variant="ghost">
							<Link to="/thread/$threadId" params={{ threadId: thread.id }}>
								<div className="grow-1 flex flex-col overflow-hidden">
									<span className="font-bold overflow-hidden whitespace-nowrap overflow-ellipsis">
										{thread.title}
									</span>
									<span className="text-sm text-muted-foreground">
										{formatDate(thread.createdAt)}
									</span>
								</div>
								<ArrowRight />
							</Link>
						</Button>
					</li>
				))}
			</ul>
		);
	}

	return (
		<p className="px-3 py-2 text-muted-foreground">There are no threads yet.</p>
	);
};
