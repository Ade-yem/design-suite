/**
 * @file analysis-api.ts
 * @description API client helpers for analysis and design result endpoints.
 */

import { apiClient } from "@/lib/api";
import type {
  AnalysisResultsEnvelope,
  MemberFullAnalysisResult,
  DesignResultsEnvelope,
} from "@/types/analysis";

export async function fetchAnalysisResults(
  projectId: string
): Promise<AnalysisResultsEnvelope> {
  const { data } = await apiClient.get<AnalysisResultsEnvelope>(
    `/api/v1/analysis/${projectId}/results`
  );
  return data;
}

export async function fetchMemberAnalysisResult(
  projectId: string,
  memberId: string
): Promise<MemberFullAnalysisResult> {
  const { data } = await apiClient.get<MemberFullAnalysisResult>(
    `/api/v1/analysis/${projectId}/results/${memberId}`
  );
  return data;
}

export async function fetchDesignResults(
  projectId: string
): Promise<DesignResultsEnvelope> {
  const { data } = await apiClient.get<DesignResultsEnvelope>(
    `/api/v1/design/${projectId}/results`
  );
  return data;
}
