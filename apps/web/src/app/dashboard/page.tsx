import ProjectCard from "@/components/dashboard/ProjectCard";

const MOCK_PROJECTS = [
  {
    id: "1",
    name: "Residential Complex A",
    description: "5-story reinforced concrete structure with basement parking.",
    lastModified: "2 hours ago",
    status: "In Progress" as const,
  },
  {
    id: "2",
    name: "Commercial Hub B",
    description: "Steel frame warehouse with office mezzanine.",
    lastModified: "1 day ago",
    status: "Review" as const,
  },
  {
    id: "3",
    name: "Villa Renovation",
    description: "Structural assessment and extension design.",
    lastModified: "3 days ago",
    status: "Completed" as const,
  },
];

export default function DashboardPage() {
  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-8 dark:bg-black">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
              Projects
            </h1>
            <p className="text-zinc-500 dark:text-zinc-400">
              Manage your structural design projects
            </p>
          </div>
          <button className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-white dark:text-black dark:hover:bg-zinc-200">
            + New Project
          </button>
        </header>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {MOCK_PROJECTS.map((project) => (
            <ProjectCard key={project.id} {...project} />
          ))}
        </div>
      </div>
    </main>
  );
}
