"use client";

import { useState } from "react";

interface HeaderProps {
  onToggleSidebar: () => void;
  projectTitle?: string;
}

export default function Header({
  onToggleSidebar,
  projectTitle = "New Project",
}: HeaderProps) {
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  return (
    <header className="flex h-14 items-center justify-between border-b border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center gap-4">
        <button
          onClick={onToggleSidebar}
          className="rounded-md p-2 text-zinc-500 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            className="h-6 w-6"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
            />
          </svg>
        </button>
        <div className="flex flex-col">
          <span className="text-xs font-semibold uppercase text-zinc-400">
            Design Suite
          </span>
          <h1 className="text-sm font-bold text-zinc-900 dark:text-white">
            {projectTitle}
          </h1>
        </div>
      </div>

      <div className="relative">
        <button
          onClick={() => setIsProfileOpen(!isProfileOpen)}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-200 text-sm font-medium text-zinc-600 hover:bg-zinc-300 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
        >
          L
        </button>

        {isProfileOpen && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setIsProfileOpen(false)}
            />
            <div className="absolute right-0 top-full z-20 mt-2 w-48 rounded-md border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-800 dark:bg-zinc-900">
              <div className="border-b border-zinc-200 px-4 py-2 dark:border-zinc-800">
                <p className="text-sm font-medium text-zinc-900 dark:text-white">
                  Lanke
                </p>
                <p className="text-xs text-zinc-500">user@example.com</p>
              </div>
              <button className="block w-full px-4 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800">
                Settings
              </button>
              <button className="block w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-zinc-100 dark:hover:bg-zinc-800">
                Sign Out
              </button>
            </div>
          </>
        )}
      </div>
    </header>
  );
}
