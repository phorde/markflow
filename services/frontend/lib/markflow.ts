export type JobStatus = "queued" | "running" | "completed" | "failed";
export type PageProcessingStatus = "pending" | "started" | "processing" | "completed" | "failed";

export interface RoutingDecisionTrace {
  page_number: number;
  task_kind: string;
  complexity: string;
  selected_model: string;
  fallback_models: string[];
  reason_lines: string[];
  benchmark_signal_summary: string;
  decision_timestamp: string;
}

export interface PageState {
  page_number: number;
  status: PageProcessingStatus;
  confidence: number;
  source: string;
  warnings: string[];
  elapsed_seconds: number;
  qa_applied: boolean;
  cleanup_applied: boolean;
  llm_review_applied: boolean;
  routing_trace: RoutingDecisionTrace | null;
}

export interface ReviewState {
  markdown_draft: string;
  edited: boolean;
  low_confidence_pages: number[];
  reprocess_requests: number[];
  export_ready: boolean;
}

export interface ArtifactLifecycleState {
  upload_state: "pending" | "ready" | "purged";
  markdown_state: "pending" | "ready" | "purged";
  report_state: "pending" | "ready" | "purged";
  expires_at: string | null;
  last_purge_attempt_at: string | null;
}

export interface JobState {
  job_id: string;
  document_name: string;
  page_count: number;
  execution_mode: string;
  routing_mode: string;
  status: JobStatus;
  pages_completed: number;
  pages_failed: number;
  page_states: PageState[];
  review_state: ReviewState;
  artifact_state: ArtifactLifecycleState;
  created_at: string;
  updated_at: string;
}

export interface SseProgressEvent {
  job_id: string;
  page_number: number;
  status: PageProcessingStatus;
  confidence: number;
  routing_decision_summary: string;
  timestamp: string;
}

export interface CreateJobRequest {
  document_name: string;
  page_count: number;
  execution_mode: "auto" | "fast" | "quality" | "local" | "remote";
  routing_mode: "fast" | "balanced" | "high-accuracy-ocr";
}

export interface CreateJobResponse {
  job_id: string;
  status: JobStatus;
}

export interface ReviewUpdateRequest {
  markdown_draft?: string;
  edited?: boolean;
  reprocess_requests?: number[];
  low_confidence_pages?: number[];
  export_ready?: boolean;
}

export interface ExportResponse {
  job_id: string;
  export_ready: boolean;
  markdown_draft: string;
  json_snapshot: Record<string, unknown>;
}

export function getApiBaseUrl() {
  const configured = process.env.NEXT_PUBLIC_MARKFLOW_API_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function createJob(request: CreateJobRequest, apiKey?: string) {
  return fetchJson<CreateJobResponse>("/api/jobs", {
    method: "POST",
    body: JSON.stringify(request),
    headers: apiKey ? { "X-API-Key": apiKey } : undefined,
  });
}

export function fetchJob(jobId: string) {
  return fetchJson<JobState>(`/api/jobs/${jobId}`);
}

export function fetchPage(jobId: string, pageNumber: number) {
  return fetchJson<PageState>(`/api/jobs/${jobId}/pages/${pageNumber}`);
}

export function updateReview(jobId: string, request: ReviewUpdateRequest) {
  return fetchJson<JobState>(`/api/jobs/${jobId}/review`, {
    method: "PATCH",
    body: JSON.stringify(request),
  });
}

export function exportJob(jobId: string) {
  return fetchJson<ExportResponse>(`/api/jobs/${jobId}/export`, {
    method: "POST",
  });
}

export function subscribeToEvents(
  jobId: string,
  onEvent: (event: SseProgressEvent) => void,
  onError?: () => void,
) {
  const source = new EventSource(`${getApiBaseUrl()}/api/jobs/${jobId}/events`);
  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as SseProgressEvent);
    } catch {
      onError?.();
    }
  };
  source.onerror = () => {
    onError?.();
  };
  return source;
}

export function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
