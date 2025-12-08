"use client";

import { useState } from "react";

interface Member {
  id: string;
  type: string;
  dimensions: {
    span?: number;
    depth?: number;
    width?: number;
    height?: number;
    thickness?: number;
  };
  supports: string[];
}

interface MemberTableProps {
  initialMembers: Member[];
  onConfirm: (members: Member[]) => void;
}

export default function MemberTable({
  initialMembers,
  onConfirm,
}: MemberTableProps) {
  const [members, setMembers] = useState<Member[]>(initialMembers);
  const [isEditing, setIsEditing] = useState(true);

  const handleDimensionChange = (
    index: number,
    field: string,
    value: string
  ) => {
    const newMembers = [...members];
    newMembers[index] = {
      ...newMembers[index],
      dimensions: {
        ...newMembers[index].dimensions,
        [field]: parseFloat(value) || 0,
      },
    };
    setMembers(newMembers);
  };

  return (
    <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h3 className="font-semibold text-zinc-900 dark:text-white">
          Extracted Members
        </h3>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Review and correct the extracted dimensions before proceeding.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-50 text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
            <tr>
              <th className="px-4 py-2 font-medium">ID</th>
              <th className="px-4 py-2 font-medium">Type</th>
              <th className="px-4 py-2 font-medium">Dimensions (mm)</th>
              <th className="px-4 py-2 font-medium">Supports</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {members.map((member, index) => (
              <tr key={member.id}>
                <td className="px-4 py-2 font-medium text-zinc-900 dark:text-white">
                  {member.id}
                </td>
                <td className="px-4 py-2 text-zinc-600 dark:text-zinc-300">
                  {member.type}
                </td>
                <td className="px-4 py-2">
                  <div className="flex gap-2">
                    {Object.entries(member.dimensions).map(([key, val]) => (
                      <div key={key} className="flex items-center gap-1">
                        <span className="text-xs text-zinc-400">{key}:</span>
                        {isEditing ? (
                          <input
                            type="number"
                            value={val}
                            onChange={(e) =>
                              handleDimensionChange(index, key, e.target.value)
                            }
                            className="w-16 rounded border border-zinc-200 bg-transparent px-1 py-0.5 text-right text-zinc-900 outline-none focus:border-zinc-400 dark:border-zinc-700 dark:text-white"
                          />
                        ) : (
                          <span className="text-zinc-900 dark:text-white">
                            {val}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-2 text-zinc-500 dark:text-zinc-400">
                  {member.supports.join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex justify-end border-t border-zinc-200 p-3 dark:border-zinc-800">
        <button
          onClick={() => onConfirm(members)}
          className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-white dark:text-black dark:hover:bg-zinc-200"
        >
          Confirm & Proceed
        </button>
      </div>
    </div>
  );
}
