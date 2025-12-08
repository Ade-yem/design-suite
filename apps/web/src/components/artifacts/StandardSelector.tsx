"use client";

interface StandardSelectorProps {
  onSelect: (standard: string) => void;
}

const STANDARDS = [
  {
    id: "bs8110",
    name: "BS 8110",
    description: "Structural use of concrete (British Standard)",
  },
  {
    id: "eurocode2",
    name: "Eurocode 2",
    description: "Design of concrete structures (EN 1992)",
  },
];

export default function StandardSelector({ onSelect }: StandardSelectorProps) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <h3 className="mb-3 font-semibold text-zinc-900 dark:text-white">
        Select Design Standard
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {STANDARDS.map((std) => (
          <button
            key={std.id}
            onClick={() => onSelect(std.id)}
            className="flex flex-col items-start rounded-md border border-zinc-200 p-3 text-left transition-colors hover:bg-zinc-50 hover:border-zinc-400 dark:border-zinc-800 dark:hover:bg-zinc-900 dark:hover:border-zinc-600"
          >
            <span className="font-medium text-zinc-900 dark:text-white">
              {std.name}
            </span>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {std.description}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
