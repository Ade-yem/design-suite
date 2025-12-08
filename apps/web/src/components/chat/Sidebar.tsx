"use client";

import Link from "next/link";
import { useState } from "react";

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
}

// Mock history data
const HISTORY = [
  { id: "1", title: "Residential Complex A", date: "Today" },
  { id: "2", title: "Commercial Hub B", date: "Yesterday" },
  { id: "3", title: "Villa Renovation", date: "Last Week" },
];

export default function Sidebar({ isOpen, onToggle }: SidebarProps) {
  return (
    <>
      {/* Mobile Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/50 lg:hidden"
          onClick={onToggle}
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-zinc-200 bg-zinc-50 transition-transform duration-300 dark:border-zinc-800 dark:bg-zinc-900 lg:static lg:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full lg:w-0 lg:border-none"
        }`}
      >
        <div className="flex h-14 items-center justify-between border-b border-zinc-200 px-4 dark:border-zinc-800">
          <span className="font-semibold text-zinc-900 dark:text-white lg:hidden">
            History
          </span>
          <button
            onClick={onToggle}
            className="rounded-md p-1 text-zinc-500 hover:bg-zinc-200 dark:text-zinc-400 dark:hover:bg-zinc-800 lg:hidden"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="h-5 w-5"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          <div className="mb-4">
            <Link
              href="/dashboard"
              className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-200 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="h-4 w-4"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18"
                />
              </svg>
              Back to Dashboard
            </Link>
          </div>

          <h3 className="mb-2 px-3 text-xs font-semibold uppercase text-zinc-400 dark:text-zinc-500">
            Recent Chats
          </h3>
          <div className="space-y-1">
            {HISTORY.map((item) => (
              <button
                key={item.id}
                className="w-full rounded-md px-3 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-200 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                <div className="truncate font-medium">{item.title}</div>
                <div className="text-xs text-zinc-500">{item.date}</div>
              </button>
            ))}
          </div>
        </div>
      </aside>
    </>
  );
}
