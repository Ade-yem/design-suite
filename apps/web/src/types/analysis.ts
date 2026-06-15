/**
 * @file analysis.ts
 * @description TypeScript types for the structural analysis and design result pipeline.
 * Mirrors the backend schema from apps/api/models/analysis/schema.py and
 * apps/api/schemas/analysis.py + design.py.
 *
 * Units convention (enforced globally):
 *   forces in kN, moments in kNm, lengths in m, section dims in mm, stresses in MPa.
 */

// ── Shared primitives ────────────────────────────────────────────────────────

export type AnalysisMemberType =
  | "beam"
  | "slab"
  | "column"
  | "wall"
  | "footing"
  | "staircase";

export type MemberCheckStatus = "pass" | "fail" | "critical" | "skipped";

// ── Analysis result types ────────────────────────────────────────────────────

/**
 * Peak internal forces at the governing section, from the FEA / coefficient solver.
 */
export interface StressResultants {
  M_max_sagging_kNm: number;
  M_max_hogging_kNm: number;
  V_max_kN: number;
  N_axial_kN: number;
  deflection_max_mm: number;
}

/**
 * Serviceability limit state deflection check.
 */
export interface SLSChecks {
  deflection_limit_mm: number;
  deflection_actual_mm: number;
  status: "pass" | "fail";
}

/**
 * A single step in the calculation audit trail.
 * Stored in backend as CalculationTraceStep.
 */
export interface CalculationTraceStep {
  step: number;
  description: string;
  formula?: string;
  inputs?: Record<string, unknown>;
  result: unknown;
  clause?: string;
}

/**
 * Per-span moment data from MomentCoefficientSolver.critical_sections.
 * Keys follow the pattern "span_1", "span_2", etc.
 */
export interface SpanCriticalSection {
  M_sagging: number;
  F: number;
}

export type MultiSpanCriticalSections = {
  [K in `span_${number}`]: SpanCriticalSection;
};

/**
 * Full analysis result for a single member, as returned by
 * GET /api/v1/analysis/{project_id}/results/{member_id}.
 */
export interface MemberFullAnalysisResult {
  member_id: string;
  member_type: AnalysisMemberType;
  analysis_method: string;
  stress_resultants: StressResultants;
  critical_sections: Record<string, unknown> | MultiSpanCriticalSections;
  reactions_kN: number[];
  governing_pattern?: string;
  SLS_checks?: SLSChecks;
  calculation_trace: CalculationTraceStep[];
  warnings: string[];
  flags: string[];
}

/**
 * Envelope returned by GET /api/v1/analysis/{project_id}/results.
 */
export interface AnalysisResultsEnvelope {
  analysis_id: string;
  design_code: string;
  members: MemberFullAnalysisResult[];
}

// ── Design result types ──────────────────────────────────────────────────────

/**
 * Shear link specification from the RC beam design.
 */
export interface ShearLinkSpec {
  diameter_mm: number;
  spacing_mm: number;
  legs: number;
  description: string;
}

/**
 * Deflection check result from design phase.
 */
export interface DesignDeflectionCheck {
  status: "pass" | "fail";
  actual_mm: number;
  limit_mm: number;
}

/**
 * RC design result for a single member from
 * GET /api/v1/design/{project_id}/results.
 */
export interface DesignMemberResult {
  member_id: string;
  member_type: AnalysisMemberType;
  status: "pass" | "fail" | "error";
  As_req?: number;
  As_prov?: number;
  reinforcement_description?: string;
  As_prime_req?: number;
  As_prime_prov?: number;
  compression_reinforcement_description?: string;
  shear_links?: ShearLinkSpec | string;
  deflection_check?: DesignDeflectionCheck;
  utilization_ratio?: number;
  notes?: string[];
  warnings?: string[];
}

/**
 * Envelope returned by GET /api/v1/design/{project_id}/results.
 */
export interface DesignResultsEnvelope {
  design_id: string;
  design_code: string;
  members: DesignMemberResult[];
}

// ── Frontend view model ──────────────────────────────────────────────────────

/**
 * Merged view combining analysis forces + design results for a single member.
 * Used by MemberCard and MemberDetailPanel.
 */
export interface MemberAnalysisView {
  member_id: string;
  member_type: AnalysisMemberType;
  status: MemberCheckStatus;
  utilization_ratio: number;
  analysis?: MemberFullAnalysisResult;
  design?: DesignMemberResult;
}
