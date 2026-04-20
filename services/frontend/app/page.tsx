"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  BadgeCheck,
  BrainCircuit,
  Download,
  FileClock,
  FileDigit,
  FileText,
  Layers3,
  Loader2,
  Play,
  RefreshCw,
  Sparkles,
  SquarePen,
  Upload,
  WandSparkles,
} from "lucide-react";
import {
  createJob,
  downloadJson,
  exportJob,
  fetchJob,
  getApiBaseUrl,
  JobState,
  PageProcessingStatus,
  subscribeToEvents,
  updateReview,
} from "@/lib/markflow";

const defaultMarkdown = `# Review Draft

## Summary
Document extracted successfully.

## Notes
- Check low-confidence pages before export.
- Confirm routing explanations and markdown output.
`;

function statusPalette(status: string) {
  switch (status) {
    case "completed":
      return "border-emerald-400/30 bg-emerald-400/10 text-emerald-100";
    case "running":
      return "border-cyan-400/30 bg-cyan-400/10 text-cyan-100";
    case "failed":
      return "border-rose-400/30 bg-rose-400/10 text-rose-100";
    default:
      return "border-white/10 bg-white/5 text-slate-100";
  }
}

function statusLabel(status: string) {
  return status.replaceAll("_", " ");
}

function confidenceLabel(value: number) {
  if (value >= 0.9) return "high";
  if (value >= 0.7) return "medium";
  if (value >= 0.4) return "low";
  return "pending";
}

function progressPercent(job: JobState | null) {
  if (!job || job.page_count === 0) return 0;
  return Math.min(100, Math.round((job.pages_completed / job.page_count) * 100));
}

function isTerminalStatus(status: string) {
  return status === "completed" || status === "failed";
}

function normalizePageCount(value: number) {
  if (!Number.isFinite(value)) return 1;
  return Math.min(500, Math.max(1, Math.trunc(value)));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

export default function Page() {
  const [apiUrl] = useState(getApiBaseUrl());
  const [documentName, setDocumentName] = useState("laudo-exemplo.pdf");
  const [pageCount, setPageCount] = useState(3);
  const [executionMode, setExecutionMode] = useState<"auto" | "fast" | "quality" | "local" | "remote">("auto");
  const [routingMode, setRoutingMode] = useState<"fast" | "balanced" | "high-accuracy-ocr">("balanced");
  const [apiKey, setApiKey] = useState("");
  const [job, setJob] = useState<JobState | null>(null);
  const [markdownDraft, setMarkdownDraft] = useState(defaultMarkdown);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSavingReview, setIsSavingReview] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [connectionMode, setConnectionMode] = useState<"idle" | "sse" | "polling">("idle");
  const [events, setEvents] = useState<Array<{ page: number; status: PageProcessingStatus; confidence: number; summary: string; time: string }>>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!job) {
      return;
    }

    let cancelled = false;
    let source: EventSource | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let sseHealthy = true;

    const startPolling = () => {
      if (pollTimer) {
        return;
      }
      setConnectionMode("polling");
      pollTimer = setInterval(async () => {
        try {
          const fresh = await fetchJob(job.job_id);
          if (!cancelled) {
            setJob(fresh);
            if (isTerminalStatus(fresh.status) && pollTimer) {
              clearInterval(pollTimer);
              pollTimer = null;
            }
          }
        } catch (pollError) {
          if (!cancelled) {
            setError(pollError instanceof Error ? pollError.message : "Falha ao atualizar estado");
          }
        }
      }, 2500);
    };

    try {
      source = subscribeToEvents(
        job.job_id,
        async (event) => {
          if (cancelled) return;
          setConnectionMode("sse");
          setEvents((current) => [
            ...current.slice(-11),
            {
              page: event.page_number,
              status: event.status,
              confidence: event.confidence,
              summary: event.routing_decision_summary,
              time: formatTime(event.timestamp),
            },
          ]);

          try {
            const fresh = await fetchJob(job.job_id);
            if (!cancelled) {
              setJob(fresh);
              if (isTerminalStatus(fresh.status)) {
                source?.close();
                source = null;
              }
            }
          } catch (refreshError) {
            if (!cancelled) {
              setError(refreshError instanceof Error ? refreshError.message : "Falha ao atualizar job");
            }
          }
        },
        () => {
          if (!cancelled && sseHealthy) {
            sseHealthy = false;
            startPolling();
          }
        },
      );
      setConnectionMode("sse");
    } catch {
      startPolling();
    }

    return () => {
      cancelled = true;
      source?.close();
      if (pollTimer) {
        clearInterval(pollTimer);
      }
    };
  }, [job?.job_id]);

  const lowConfidencePages = useMemo(
    () => job?.review_state.low_confidence_pages ?? [],
    [job],
  );

  const reprocessRequests = useMemo(
    () => job?.review_state.reprocess_requests ?? [],
    [job],
  );

  async function submitJob() {
    setIsSubmitting(true);
    setError(null);
    try {
      const normalizedPageCount = normalizePageCount(pageCount);
      if (!documentName.trim()) {
        throw new Error("Informe o nome do documento.");
      }
      if (normalizedPageCount !== pageCount) {
        setPageCount(normalizedPageCount);
      }
      const response = await createJob(
        {
          document_name: documentName.trim(),
          page_count: normalizedPageCount,
          execution_mode: executionMode,
          routing_mode: routingMode,
        },
        apiKey.trim() || undefined,
      );
      const created = await fetchJob(response.job_id);
      setJob(created);
      setMarkdownDraft(created.review_state.markdown_draft || defaultMarkdown);
      setEvents([]);
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Falha ao criar job");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function saveReview() {
    if (!job) return;
    setIsSavingReview(true);
    setError(null);
    try {
      const updated = await updateReview(job.job_id, {
        markdown_draft: markdownDraft,
        edited: true,
        low_confidence_pages: lowConfidencePages,
        reprocess_requests: reprocessRequests,
        export_ready: job.status === "completed" && lowConfidencePages.length === 0,
      });
      setJob(updated);
      setMarkdownDraft(updated.review_state.markdown_draft || markdownDraft);
    } catch (reviewError) {
      setError(reviewError instanceof Error ? reviewError.message : "Falha ao salvar revisão");
    } finally {
      setIsSavingReview(false);
    }
  }

  async function triggerExport() {
    if (!job) return;
    setIsExporting(true);
    setError(null);
    try {
      const exported = await exportJob(job.job_id);
      downloadJson(`${exported.job_id}.markflow-export.json`, exported);
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Falha ao exportar");
    } finally {
      setIsExporting(false);
    }
  }

  async function requestReprocess(pageNumber: number) {
    if (!job) return;
    try {
      const nextPages = Array.from(new Set([...reprocessRequests, pageNumber]));
      const updated = await updateReview(job.job_id, {
        markdown_draft: markdownDraft,
        edited: true,
        low_confidence_pages: lowConfidencePages,
        reprocess_requests: nextPages,
        export_ready: false,
      });
      setJob(updated);
    } catch (reprocessError) {
      setError(reprocessError instanceof Error ? reprocessError.message : "Falha ao solicitar reprocessamento");
    }
  }

  async function approveLowConfidencePage(pageNumber: number) {
    if (!job) return;
    try {
      const nextLowConfidencePages = lowConfidencePages.filter((page) => page !== pageNumber);
      const updated = await updateReview(job.job_id, {
        markdown_draft: markdownDraft,
        edited: true,
        low_confidence_pages: nextLowConfidencePages,
        reprocess_requests: reprocessRequests.filter((page) => page !== pageNumber),
        export_ready: job.status === "completed" && nextLowConfidencePages.length === 0,
      });
      setJob(updated);
    } catch (approvalError) {
      setError(approvalError instanceof Error ? approvalError.message : "Falha ao aprovar página");
    }
  }

  return (
    <main className="min-h-screen overflow-hidden text-white">
      <div className="absolute inset-0 bg-markflow-grid bg-grid opacity-40 [mask-image:radial-gradient(circle_at_center,black,transparent_85%)]" />
      <div className="relative mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <header className="glass-panel relative overflow-hidden rounded-[2rem] p-6">
          <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-cyan-400/20 blur-3xl" />
          <div className="absolute -bottom-10 left-1/3 h-36 w-36 rounded-full bg-fuchsia-500/10 blur-3xl" />
          <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl space-y-4">
              <span className="section-label">MarkFlow Web Platform</span>
              <h1 className="text-4xl font-bold tracking-tight text-white sm:text-5xl">
                OCR-first workflow dashboard with review-before-export.
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-slate-300 sm:text-base">
                The frontend planned in the GSD roadmap now has a local entry point: submit a job,
                watch SSE progress, review the draft, and export the current state snapshot. API base:
                <span className="mono ml-2 rounded-full border border-white/10 bg-black/30 px-2 py-1 text-cyan-200">
                  {apiUrl}
                </span>
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3 lg:min-w-[28rem]">
              <div className="glass-panel rounded-3xl p-4">
                <div className="text-xs uppercase tracking-[0.28em] text-slate-400">Pipeline</div>
                <div className="mt-2 text-2xl font-semibold">Upload → Review → Export</div>
              </div>
              <div className="glass-panel rounded-3xl p-4">
                <div className="text-xs uppercase tracking-[0.28em] text-slate-400">Transport</div>
                <div className="mt-2 text-2xl font-semibold">SSE + polling fallback</div>
              </div>
              <div className="glass-panel rounded-3xl p-4">
                <div className="text-xs uppercase tracking-[0.28em] text-slate-400">Boundary</div>
                <div className="mt-2 text-2xl font-semibold">API owns state</div>
              </div>
            </div>
          </div>
        </header>

        <section className="mt-6 grid gap-6 xl:grid-cols-[1.05fr_1.1fr_0.95fr]">
          <div className="glass-panel rounded-[2rem] p-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <span className="section-label">1. Submit</span>
                <h2 className="mt-2 text-2xl font-semibold">Documento e parâmetros</h2>
              </div>
              <span className="chip animate-pulseSoft">
                <Upload className="h-3.5 w-3.5" />
                Local only
              </span>
            </div>

            <div className="mt-6 space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-2">
                  <span className="field-label">Nome do documento</span>
                  <input
                    className="input-shell"
                    value={documentName}
                    onChange={(event) => setDocumentName(event.target.value)}
                    placeholder="laudo-exemplo.pdf"
                  />
                </label>
                <label className="space-y-2">
                  <span className="field-label">Páginas</span>
                  <input
                    className="input-shell"
                    type="number"
                    min={1}
                    max={500}
                    value={pageCount}
                    onChange={(event) => setPageCount(normalizePageCount(Number(event.target.value)))}
                  />
                </label>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-2">
                  <span className="field-label">Modo de execução</span>
                  <select
                    className="input-shell"
                    value={executionMode}
                    onChange={(event) => setExecutionMode(event.target.value as typeof executionMode)}
                  >
                    <option value="auto">auto</option>
                    <option value="fast">fast</option>
                    <option value="quality">quality</option>
                    <option value="local">local</option>
                    <option value="remote">remote</option>
                  </select>
                </label>
                <label className="space-y-2">
                  <span className="field-label">Routing</span>
                  <select
                    className="input-shell"
                    value={routingMode}
                    onChange={(event) => setRoutingMode(event.target.value as typeof routingMode)}
                  >
                    <option value="fast">fast</option>
                    <option value="balanced">balanced</option>
                    <option value="high-accuracy-ocr">high-accuracy-ocr</option>
                  </select>
                </label>
              </div>

              <label className="space-y-2">
                <span className="field-label">API key (opcional, somente em memória)</span>
                <input
                  className="input-shell mono"
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="sk-..."
                />
              </label>

              <div className="rounded-3xl border border-dashed border-white/15 bg-white/5 p-4">
                <div className="flex items-start gap-3 text-sm text-slate-300">
                  <FileText className="mt-0.5 h-4 w-4 text-cyan-300" />
                  <p>
                    v1 usa metadata de submissão, não upload binário completo ainda. O layout já está
                    desenhado para a etapa de upload real prevista no plano.
                  </p>
                </div>
              </div>

              <button className="btn-primary w-full" onClick={submitJob} disabled={isSubmitting}>
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Iniciar processamento
              </button>
            </div>
          </div>

          <div className="space-y-6">
            <div className="glass-panel rounded-[2rem] p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <span className="section-label">2. Processing</span>
                  <h2 className="mt-2 text-2xl font-semibold">Estado canônico</h2>
                </div>
                <div className={`chip ${statusPalette(job?.status ?? "queued")}`}>
                  <BadgeCheck className="h-3.5 w-3.5" />
                  {job ? statusLabel(job.status) : "waiting"}
                </div>
              </div>

              <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                  <div className="text-xs uppercase tracking-[0.28em] text-slate-400">job id</div>
                  <div className="mt-2 break-all text-sm text-white">{job?.job_id ?? "—"}</div>
                </div>
                <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                  <div className="text-xs uppercase tracking-[0.28em] text-slate-400">progress</div>
                  <div className="mt-2 text-2xl font-semibold text-cyan-200">{progressPercent(job)}%</div>
                </div>
                <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                  <div className="text-xs uppercase tracking-[0.28em] text-slate-400">completed</div>
                  <div className="mt-2 text-2xl font-semibold text-emerald-200">{job?.pages_completed ?? 0}</div>
                </div>
                <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                  <div className="text-xs uppercase tracking-[0.28em] text-slate-400">failed</div>
                  <div className="mt-2 text-2xl font-semibold text-rose-200">{job?.pages_failed ?? 0}</div>
                </div>
              </div>

              {job ? (
                <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-300">
                  <span className="chip">created {formatDateTime(job.created_at)}</span>
                  <span className="chip">updated {formatDateTime(job.updated_at)}</span>
                </div>
              ) : null}

              <div className="mt-6 h-2 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-teal-400 to-emerald-400 transition-all duration-500"
                  style={{ width: `${progressPercent(job)}%` }}
                />
              </div>

              <div className="mt-6 grid gap-4 lg:grid-cols-2">
                <div className="rounded-3xl border border-white/10 bg-slate-950/50 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                    <Layers3 className="h-4 w-4 text-cyan-300" />
                    Page states
                  </div>
                  <div className="mt-4 space-y-3">
                    {(job?.page_states ?? []).map((page) => (
                      <div key={page.page_number} className="rounded-2xl border border-white/10 bg-white/5 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="font-medium text-white">Page {page.page_number}</div>
                          <span className={`chip ${statusPalette(page.status)}`}>{statusLabel(page.status)}</span>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-300">
                          <span className="chip">
                            <BrainCircuit className="h-3.5 w-3.5" />
                            confidence {confidenceLabel(page.confidence)} ({Math.round(page.confidence * 100)}%)
                          </span>
                          {page.routing_trace ? (
                            <span className="chip">
                              <FileDigit className="h-3.5 w-3.5" />
                              {page.routing_trace.benchmark_signal_summary || "routing trace"}
                            </span>
                          ) : null}
                        </div>
                        {page.warnings.length > 0 ? (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {page.warnings.map((warning) => (
                              <span key={warning} className="chip border-amber-400/20 bg-amber-500/10 text-amber-100">
                                <AlertCircle className="h-3.5 w-3.5" />
                                {warning}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                    {!job?.page_states?.length ? (
                      <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-sm text-slate-400">
                        Submit a job to visualize page state transitions.
                      </div>
                    ) : null}
                  </div>
                </div>

                <div className="rounded-3xl border border-white/10 bg-slate-950/50 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                    <Sparkles className="h-4 w-4 text-cyan-300" />
                    Live events
                  </div>
                  <div className="mt-4 space-y-3">
                    {events.length > 0 ? (
                      events.map((event, index) => (
                        <div key={`${event.page}-${event.time}-${index}`} className="rounded-2xl border border-white/10 bg-white/5 p-3">
                          <div className="flex items-center justify-between gap-3 text-sm">
                            <span className="chip">page {event.page}</span>
                            <span className={`chip ${statusPalette(event.status)}`}>{statusLabel(event.status)}</span>
                          </div>
                          <p className="mt-2 text-sm text-slate-200">{event.summary}</p>
                          <div className="mt-2 text-xs text-slate-400">{event.time}</div>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-sm text-slate-400">
                        SSE events will appear here when a job starts.
                      </div>
                    )}
                  </div>
                  <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-3 text-xs text-slate-300">
                    Connection: <span className="font-semibold text-cyan-200">{connectionMode}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="glass-panel rounded-[2rem] p-5">
              <div className="flex items-center gap-3 text-sm font-semibold text-slate-100">
                <WandSparkles className="h-4 w-4 text-cyan-300" />
                Explainability
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                  <div className="text-xs uppercase tracking-[0.28em] text-slate-400">routing</div>
                  <div className="mt-2 text-sm text-slate-100">
                    {job?.routing_mode ?? "balanced"} / {job?.execution_mode ?? "auto"}
                  </div>
                </div>
                <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                  <div className="text-xs uppercase tracking-[0.28em] text-slate-400">review gate</div>
                  <div className="mt-2 text-sm text-slate-100">
                    {job?.review_state.export_ready ? "ready for export" : "needs review"}
                  </div>
                </div>
                <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                  <div className="text-xs uppercase tracking-[0.28em] text-slate-400">low confidence</div>
                  <div className="mt-2 text-sm text-slate-100">
                    {lowConfidencePages.length ? lowConfidencePages.join(", ") : "none"}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="glass-panel rounded-[2rem] p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <span className="section-label">3. Review</span>
                  <h2 className="mt-2 text-2xl font-semibold">Markdown preview</h2>
                </div>
                <button
                  className="btn-secondary"
                  onClick={() => setMarkdownDraft((current) => current || defaultMarkdown)}
                >
                  <FileText className="h-4 w-4" />
                  Recarregar
                </button>
              </div>

              <div className="mt-4 rounded-3xl border border-white/10 bg-slate-950/60 p-4">
                <textarea
                  className="min-h-[16rem] w-full resize-y rounded-2xl border border-white/10 bg-transparent p-3 text-sm leading-6 text-slate-100 outline-none focus:border-cyan-400/60"
                  value={markdownDraft}
                  onChange={(event) => setMarkdownDraft(event.target.value)}
                  placeholder="A revisão editável aparece aqui."
                />
              </div>

              <div className="mt-4 flex flex-wrap gap-3">
                <button className="btn-primary" onClick={saveReview} disabled={isSavingReview || !job}>
                  {isSavingReview ? <Loader2 className="h-4 w-4 animate-spin" /> : <SquarePen className="h-4 w-4" />}
                  Salvar revisão
                </button>
                <button
                  className="btn-secondary"
                  onClick={triggerExport}
                  disabled={isExporting || !job || job.status !== "completed" || !job.review_state.export_ready}
                >
                  {isExporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                  Exportar snapshot
                </button>
              </div>

              <div className="mt-4 rounded-3xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300">
                <div className="flex items-center gap-2 text-slate-100">
                  <BrainCircuit className="h-4 w-4 text-cyan-300" />
                  Review-before-export
                </div>
                <p className="mt-2 leading-6">
                  A exportação fica bloqueada até o job terminar e a revisão ficar consistente. A UI já
                  permite editar o markdown e solicitar reprocessamento das páginas com baixa confiança.
                </p>
              </div>
            </div>

            <div className="glass-panel rounded-[2rem] p-5">
              <div className="flex items-center gap-3 text-sm font-semibold text-slate-100">
                <FileClock className="h-4 w-4 text-cyan-300" />
                Page controls
              </div>
              <div className="mt-4 space-y-3">
                {(job?.page_states ?? []).map((page) => {
                  const isLowConfidence = lowConfidencePages.includes(page.page_number);
                  const isQueuedForReprocess = reprocessRequests.includes(page.page_number);
                  return (
                    <div key={page.page_number} className="rounded-3xl border border-white/10 bg-white/5 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="font-semibold text-white">Página {page.page_number}</div>
                          <div className="mt-1 text-xs text-slate-400">
                            {page.routing_trace?.selected_model || "model pending"}
                          </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`chip ${statusPalette(page.status)}`}>{statusLabel(page.status)}</span>
                          <span className="chip">{Math.round(page.confidence * 100)}%</span>
                        </div>
                      </div>

                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          className="btn-secondary text-xs"
                          onClick={() => requestReprocess(page.page_number)}
                          disabled={!job}
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                          Reprocessar
                        </button>
                        {isLowConfidence ? (
                          <button
                            className="btn-secondary text-xs"
                            onClick={() => approveLowConfidencePage(page.page_number)}
                            disabled={!job}
                          >
                            <BadgeCheck className="h-3.5 w-3.5" />
                            Aprovar
                          </button>
                        ) : null}
                        <span className={`chip ${isLowConfidence ? "border-amber-400/20 bg-amber-500/10 text-amber-100" : ""}`}>
                          {isLowConfidence ? "low confidence" : "stable"}
                        </span>
                        {isQueuedForReprocess ? <span className="chip">queued</span> : null}
                      </div>
                    </div>
                  );
                })}
                {!job?.page_states?.length ? (
                  <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-sm text-slate-400">
                    A lista de páginas aparece após submeter um job.
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </section>

        {error ? (
          <div className="mt-6 rounded-3xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {error}
          </div>
        ) : null}

        <footer className="mt-6 flex flex-col gap-3 border-t border-white/10 py-4 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <ArrowRight className="h-3.5 w-3.5" />
            MarkFlow Web UI local preview
          </div>
          <div className="flex items-center gap-3">
            <span className="chip border-white/10 bg-white/5 text-slate-100">FastAPI API</span>
            <span className="chip border-white/10 bg-white/5 text-slate-100">Next.js frontend</span>
            <span className="chip border-white/10 bg-white/5 text-slate-100">SSE + polling</span>
          </div>
        </footer>
      </div>
    </main>
  );
}
