import Link from "next/link";

interface ProjectCardProps {
  id: string;
  name: string;
  description: string;
  lastModified: string;
  status: "In Progress" | "Completed" | "Review";
}

export default function ProjectCard({
  id,
  name,
  description,
  lastModified,
  status,
}: ProjectCardProps) {
  return (
    <Link
      href={`/chat?projectId=${id}`}
      className="group relative flex flex-col justify-between rounded-xl border border-zinc-200 bg-white p-6 transition-all hover:border-zinc-400 hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700"
    >
      <div>
        <div className="flex items-start justify-between">
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
            {name}
          </h3>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
              status === "Completed"
                ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                : status === "Review"
                ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400"
                : "bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-300"
            }`}
          >
            {status}
          </span>
        </div>
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          {description}
        </p>
      </div>
      <div className="mt-4 flex items-center text-xs text-zinc-400">
        <span>Last modified {lastModified}</span>
      </div>
    </Link>
  );
}
