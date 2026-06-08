"use client";

import { useState } from "react";
import { ChevronDown, ChevronLeft, Layers } from "lucide-react";
import type { GeometricMember, MemberType } from "@/types/canvas";
import { useUIStore } from "@/stores/uiStore";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";

interface MembersPanelProps {
  members: GeometricMember[];
  selectedMemberId: string | null;
  onSelectMember: (id: string | null) => void;
  onZoomToMember: (id: string) => void;
}

type MemberGroup = MemberType;

const GROUP_ORDER: MemberGroup[] = [
  "beam",
  "column",
  "slab",
  "wall",
  "footing",
  "staircase",
  "void",
];

const GROUP_LABELS: Record<MemberGroup, string> = {
  beam: "Beams",
  column: "Columns",
  slab: "Slabs",
  wall: "Walls",
  footing: "Footings",
  staircase: "Staircases",
  void: "Openings",
};

// Helper: group members by type
function groupByType(members: GeometricMember[]): Record<MemberGroup, GeometricMember[]> {
  const result: Record<MemberGroup, GeometricMember[]> = {
    beam: [],
    column: [],
    slab: [],
    wall: [],
    footing: [],
    staircase: [],
    void: [],
  };

  for (const member of members) {
    if (result[member.member_type]) {
      result[member.member_type].push(member);
    }
  }

  return result;
}

export const MembersPanel: React.FC<MembersPanelProps> = ({
  members,
  selectedMemberId,
  onSelectMember,
  onZoomToMember,
}) => {
  const {
    membersPanelExpanded,
    setMembersPanelExpanded,
    pipelineRailExpanded,
  } = useUIStore();

  const grouped = groupByType(members);
  const visibleGroups = GROUP_ORDER.filter((type) => grouped[type].length > 0);
  const totalCount = members.length;

  if (!membersPanelExpanded) {
    if (!pipelineRailExpanded) {
      return null;
    }
    return (
      <div className="w-12 h-full flex flex-col bg-muted/40 border-r border-border shrink-0 items-center py-4">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={() => setMembersPanelExpanded(true)}
              className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              aria-label="Expand Members list"
            >
              <Layers className="h-4 w-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" align="center">
            Expand Members list
          </TooltipContent>
        </Tooltip>
      </div>
    );
  }

  return (
    <div className="w-64 flex flex-col border-r border-border bg-muted/20 overflow-hidden shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="text-xs font-semibold text-foreground/80">
          MEMBERS
          <span className="ml-2 text-foreground/50">{totalCount} total</span>
        </div>
        <button
          onClick={() => setMembersPanelExpanded(false)}
          className="p-1 hover:bg-muted/60 rounded transition-colors"
          title="Collapse Members panel"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>

      {/* Groups */}
      <div className="flex-1 overflow-y-auto space-y-3 p-3">
        {visibleGroups.map((type) => (
          <MemberGroup
            key={type}
            type={type}
            members={grouped[type]}
            selectedMemberId={selectedMemberId}
            onSelectMember={onSelectMember}
            onZoomToMember={onZoomToMember}
          />
        ))}
      </div>
    </div>
  );
};

interface MemberGroupProps {
  type: MemberGroup;
  members: GeometricMember[];
  selectedMemberId: string | null;
  onSelectMember: (id: string | null) => void;
  onZoomToMember: (id: string) => void;
}

const MemberGroup: React.FC<MemberGroupProps> = ({
  type,
  members,
  selectedMemberId,
  onSelectMember,
  onZoomToMember,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const typeLabel = GROUP_LABELS[type];

  return (
    <div>
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-foreground hover:bg-muted/60 rounded transition-colors"
      >
        <ChevronDown
          className={`h-3 w-3 transition-transform ${isCollapsed ? "-rotate-90" : ""}`}
        />
        <span>{typeLabel}</span>
        <span className="ml-auto text-xs text-foreground/50">{members.length}</span>
      </button>

      {!isCollapsed && (
        <div className="space-y-1 pl-6">
          {members.map((member) => (
            <button
              key={member.member_id}
              onClick={() => {
                onSelectMember(member.member_id);
                onZoomToMember(member.member_id);
              }}
              className={`w-full text-left text-xs px-3 py-1.5 rounded transition-colors whitespace-nowrap overflow-hidden text-ellipsis ${
                selectedMemberId === member.member_id
                  ? "bg-blue-500/30 text-blue-200 font-medium"
                  : "text-foreground/70 hover:bg-muted/60 hover:text-foreground"
              }`}
              title={member.member_id}
            >
              {member.member_id}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
