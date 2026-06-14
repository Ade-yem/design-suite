/**
 * @file analysisStore.ts
 * @description Zustand store for the analysis & calculation verification view.
 *
 * Manages fetched analysis/design results, member selection, diagram tab state,
 * and list filtering. NOT persisted — results are always re-fetched per session.
 */

import { create } from "zustand";
import { fetchAnalysisResults, fetchDesignResults } from "@/lib/analysis-api";
import type {
  MemberFullAnalysisResult,
  DesignMemberResult,
  AnalysisResultsEnvelope,
  DesignResultsEnvelope,
  MemberCheckStatus,
} from "@/types/analysis";

export type DiagramTab =
  | "overview"
  | "bmd"
  | "sfd"
  | "deflection"
  | "loads"
  | "rebar"
  | "calc";

// ── Helper: derive utilization ratio from available data ────────────────────

function deriveUtilizationRatio(
  analysis?: MemberFullAnalysisResult,
  design?: DesignMemberResult
): number {
  // Prefer explicit design ratio
  if (design?.utilization_ratio != null) return design.utilization_ratio;

  // Fall back to SLS deflection ratio from analysis
  if (analysis?.SLS_checks) {
    const { deflection_actual_mm, deflection_limit_mm } = analysis.SLS_checks;
    if (deflection_limit_mm > 0)
      return parseFloat((deflection_actual_mm / deflection_limit_mm).toFixed(3));
  }

  // Rough estimate: flag members with large forces relative to a 300×500mm section
  if (analysis?.stress_resultants) {
    const { M_max_sagging_kNm, V_max_kN } = analysis.stress_resultants;
    // Simplified moment capacity estimate for fcu=30, b=300, d=440
    const M_cap_est = (0.156 * 30 * 300 * 440 * 440) / 1e6; // ~272 kNm
    const V_cap_est = (0.4 * 300 * 440) / 1e3; // ~53 kN (rough)
    return parseFloat(
      Math.max(M_max_sagging_kNm / M_cap_est, V_max_kN / V_cap_est).toFixed(3)
    );
  }

  return 0;
}

function deriveStatus(
  analysis?: MemberFullAnalysisResult,
  design?: DesignMemberResult
): MemberCheckStatus {
  if (design) {
    if (design.status === "fail") return "fail";
    if (design.status === "pass") return "pass";
  }
  if (analysis?.SLS_checks?.status === "fail") return "fail";
  const ratio = deriveUtilizationRatio(analysis, design);
  if (ratio > 1.1) return "critical";
  if (ratio > 1.0) return "fail";
  return "pass";
}

// ── State & Actions interfaces ───────────────────────────────────────────────

interface AnalysisState {
  analysisResults: AnalysisResultsEnvelope | null;
  designResults: DesignResultsEnvelope | null;
  memberAnalysisMap: Map<string, MemberFullAnalysisResult>;
  memberDesignMap: Map<string, DesignMemberResult>;

  selectedMemberId: string | null;
  activeTab: DiagramTab;

  /** Whether the member analysis drawer is open over the workspace. */
  isDrawerOpen: boolean;

  isLoading: boolean;
  isDesignLoading: boolean;
  error: string | null;
}

interface AnalysisActions {
  fetchResults: (projectId: string) => Promise<void>;
  fetchDesign: (projectId: string) => Promise<void>;
  selectMember: (memberId: string | null) => void;
  /** Open the analysis drawer focused on a member (used by canvas click). */
  openForMember: (memberId: string) => void;
  closeDrawer: () => void;
  setActiveTab: (tab: DiagramTab) => void;

  getSelectedAnalysis: () => MemberFullAnalysisResult | null;
  getSelectedDesign: () => DesignMemberResult | null;
  getUtilizationRatio: (memberId: string) => number;
  getMemberStatus: (memberId: string) => MemberCheckStatus;
  clear: () => void;
}

const INITIAL: AnalysisState = {
  analysisResults: null,
  designResults: null,
  memberAnalysisMap: new Map(),
  memberDesignMap: new Map(),
  selectedMemberId: null,
  activeTab: "overview",
  isDrawerOpen: false,
  isLoading: false,
  isDesignLoading: false,
  error: null,
};

// ── Store ────────────────────────────────────────────────────────────────────

export const useAnalysisStore = create<AnalysisState & AnalysisActions>()(
  (set, get) => ({
    ...INITIAL,

    fetchResults: async (projectId) => {
      set({ isLoading: true, error: null });
      try {
        const data = await fetchAnalysisResults(projectId);
        const map = new Map<string, MemberFullAnalysisResult>();
        for (const m of data.members ?? []) map.set(m.member_id, m);
        set({ analysisResults: data, memberAnalysisMap: map, isLoading: false });
      } catch (e) {
        set({
          error:
            e instanceof Error ? e.message : "Failed to load analysis results",
          isLoading: false,
        });
      }
    },

    fetchDesign: async (projectId) => {
      set({ isDesignLoading: true });
      try {
        const data = await fetchDesignResults(projectId);
        const map = new Map<string, DesignMemberResult>();
        for (const m of data.members ?? []) map.set(m.member_id, m);
        set({ designResults: data, memberDesignMap: map, isDesignLoading: false });
      } catch {
        set({ isDesignLoading: false }); // Non-fatal — design may not be complete yet
      }
    },

    selectMember: (memberId) =>
      set({ selectedMemberId: memberId, activeTab: "overview" }),

    openForMember: (memberId) =>
      set({
        selectedMemberId: memberId,
        activeTab: "overview",
        isDrawerOpen: true,
      }),

    closeDrawer: () => set({ isDrawerOpen: false }),

    setActiveTab: (tab) => set({ activeTab: tab }),

    getSelectedAnalysis: () => {
      const { selectedMemberId, memberAnalysisMap } = get();
      if (!selectedMemberId) return null;
      return memberAnalysisMap.get(selectedMemberId) ?? null;
    },

    getSelectedDesign: () => {
      const { selectedMemberId, memberDesignMap } = get();
      if (!selectedMemberId) return null;
      return memberDesignMap.get(selectedMemberId) ?? null;
    },

    getUtilizationRatio: (memberId) => {
      const { memberAnalysisMap, memberDesignMap } = get();
      return deriveUtilizationRatio(
        memberAnalysisMap.get(memberId),
        memberDesignMap.get(memberId)
      );
    },

    getMemberStatus: (memberId) => {
      const { memberAnalysisMap, memberDesignMap } = get();
      return deriveStatus(
        memberAnalysisMap.get(memberId),
        memberDesignMap.get(memberId)
      );
    },

    clear: () => set(INITIAL),
  })
);
