export interface Project {
  project_id: string;
  name: string;
  reference: string;
  client: string;
  design_code: string;
  pipeline_status: string;
  pipeline_status_ordinal: number;
  created_at: string;
  updated_at: string;
  member_count: number;
}

export interface ProjectListItem {
  project_id: string;
  name: string;
  reference: string;
  pipeline_status: string;
  updated_at: string;
}

export interface CreateProjectPayload {
  name: string;
  reference: string;
  client: string;
  design_code: "BS8110" | "EC2";
}

export interface JobStatus {
  job_id: string;
  job_type: string;
  status: "queued" | "running" | "complete" | "failed" | "cancelled";
  progress_pct: number;
  current_step: string;
  result_url: string | null;
  errors: string[];
}
