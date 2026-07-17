import {
  AlertCircle,
  CheckCircle2,
  Filter,
  Loader2,
  Search,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  createCrawlRun,
  fetchCrawlRun,
  type CrawlRunStats,
} from "../api/crawler";

type CrawlerModalProps = {
  open: boolean;
  target: string;
  llmConfigured: boolean;
  onClose: () => void;
  onSuccess: () => void;
};

type ModalStatus =
  "idle" | "submitting" | "running" | "success" | "partial_success" | "failed";

const TARGETS = ["APT28", "Kimsuky", "Lazarus"];
const SOURCES = [
  ["奇安信", "qianxin"],
  ["The Hacker News", "thehackernews"],
  ["Unit 42", "unit42"],
  ["FreeBuf", "freebuf"],
  ["Chainalysis", "chainalysis"],
  ["TRM Labs", "trmlabs"],
  ["Microsoft", "microsoft"],
  ["Securelist", "securelist"],
  ["CrowdStrike", "crowdstrike"],
  ["Group-IB", "groupib"],
  ["OFAC", "ofac"],
  ["FBI", "fbi"],
] as const;

const POLL_INTERVAL_MS = 1000;

export default function CrawlerModal({
  open,
  target,
  llmConfigured,
  onClose,
  onSuccess,
}: CrawlerModalProps) {
  const [selectedTarget, setSelectedTarget] = useState(target);
  const [limit, setLimit] = useState(5);
  const [selectedSources, setSelectedSources] = useState<number[]>([0]);
  const [filter, setFilter] = useState(false);
  const [status, setStatus] = useState<ModalStatus>("idle");
  const [run, setRun] = useState<CrawlRunStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const requestGenerationRef = useRef(0);

  const sources = useMemo(
    () => selectedSources.reduce((mask, index) => mask | (1 << index), 0),
    [selectedSources],
  );
  const isRunning = status === "running";
  const isBusy = isRunning || status === "submitting";
  const progress = run?.progress;
  const progressPercent =
    progress && progress.total > 0
      ? Math.min(
          100,
          progress.percent ??
            Math.round((progress.current / progress.total) * 100),
        )
      : 0;
  const recentEvents = (run?.events ?? []).slice(-6).reverse();

  useEffect(() => {
    if (open) {
      setSelectedTarget(target);
      setStatus("idle");
      setRun(null);
      setError(null);
    }
    return () => {
      requestGenerationRef.current += 1;
      requestControllerRef.current?.abort();
      requestControllerRef.current = null;
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [open, target]);

  if (!open) return null;

  const toggleSource = (index: number) => {
    setSelectedSources((current) =>
      current.includes(index)
        ? current.filter((item) => item !== index)
        : [...current, index],
    );
  };

  const handleRun = async () => {
    if (!llmConfigured || isBusy || sources === 0 || limit < 1) return;
    setStatus("submitting");
    setRun(null);
    setError(null);
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const generation = requestGenerationRef.current + 1;
    requestGenerationRef.current = generation;
    const isCurrent = () =>
      requestGenerationRef.current === generation && !controller.signal.aborted;
    try {
      const created = await createCrawlRun(
        {
          keyword: selectedTarget,
          limit,
          sources,
          filter,
        },
        { signal: controller.signal },
      );
      const runId = created.crawl_run_id;
      const poll = async () => {
        try {
          const current = await fetchCrawlRun(runId, {
            signal: controller.signal,
          });
          if (!isCurrent()) return;
          setRun(current);
          if (current.status === "succeeded") {
            setStatus("success");
            onSuccess();
            return;
          }
          if (current.status === "partial_success") {
            setStatus("partial_success");
            setError(current.error_message);
            onSuccess();
            return;
          }
          if (current.status === "failed") {
            setStatus("failed");
            setError(current.error_message ?? "采集任务失败");
            return;
          }
          setStatus("running");
          pollTimerRef.current = window.setTimeout(poll, POLL_INTERVAL_MS);
        } catch (cause: unknown) {
          if (!isCurrent()) return;
          setStatus("failed");
          setError(cause instanceof Error ? cause.message : "查询采集任务失败");
        }
      };
      setStatus("running");
      await poll();
    } catch (cause: unknown) {
      if (!isCurrent()) return;
      setStatus("failed");
      setError(cause instanceof Error ? cause.message : "创建采集任务失败");
    }
  };

  const handleClose = () => {
    if (isBusy) return;
    onClose();
  };

  return (
    <div className="crawler-modal-backdrop" onClick={handleClose}>
      <section
        aria-label="流水线弹窗"
        className="crawler-modal"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="crawler-modal-header">
          <div>
            <h2>流水线</h2>
          </div>
          <button
            className="crawler-close"
            type="button"
            aria-label="关闭"
            onClick={handleClose}
          >
            <X size={18} />
          </button>
        </div>

        <p className="crawler-intro">
          选择目标组织、采集数量和公开来源，启动一次情报采集任务。
        </p>

        {!llmConfigured ? (
          <div className="crawler-result crawler-result-warning" role="status">
            <AlertCircle size={16} /> 需要有效 LLM 配置后才能运行流水线。
          </div>
        ) : null}

        <div className="crawler-form-grid">
          <label className="crawler-field">
            <span>目标组织</span>
            <select
              aria-label="目标组织"
              value={selectedTarget}
              disabled={isBusy}
              onChange={(event) => setSelectedTarget(event.target.value)}
            >
              {TARGETS.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <label className="crawler-field">
            <span>每个来源最多采集</span>
            <input
              type="number"
              min={1}
              max={50}
              value={limit}
              disabled={isBusy}
              onChange={(event) => setLimit(Number(event.target.value))}
            />
          </label>
        </div>

        <fieldset className="crawler-sources">
          <legend>公开来源</legend>
          <div className="crawler-source-grid">
            {SOURCES.map(([label], index) => (
              <label className="crawler-source" key={label}>
                <input
                  type="checkbox"
                  aria-label={label}
                  checked={selectedSources.includes(index)}
                  disabled={isBusy}
                  onChange={() => toggleSource(index)}
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <label className="crawler-filter-toggle">
          <input
            type="checkbox"
            aria-label="启用 LLM 相关性过滤"
            checked={filter}
            disabled={isBusy}
            onChange={(event) => setFilter(event.target.checked)}
          />
          <Filter size={16} />
          <span>
            <strong>启用 LLM 相关性过滤</strong>
          </span>
        </label>

        {status === "submitting" || isRunning ? (
          <div className="crawler-progress" role="status">
            <div className="crawler-progress-title">
              <Loader2 size={16} className="loader-spin" />
              <strong>
                {status === "submitting"
                  ? "正在提交采集任务"
                  : (progress?.message ?? "任务正在执行")}
              </strong>
              {progress ? (
                <span>
                  {progress.current}/{progress.total} {progress.message} 目标：
                  {progress.target}
                  {progress.source ? ` 来源：${progress.source}` : ""}
                </span>
              ) : (
                <span>任务正在执行</span>
              )}
            </div>
            <div className="crawler-progress-track">
              <div
                style={{
                  width:
                    status === "submitting" ? "33%" : `${progressPercent}%`,
                }}
              />
            </div>
            <p>任务正在执行，页面会自动同步 backend 状态。</p>
          </div>
        ) : null}

        {run ? (
          <section className="crawler-debug" aria-label="流水线调试信息">
            <div className="crawler-debug-ids">
              <span className="crawler-debug-id">
                采集任务 {run.crawl_run_id}
              </span>
              {run.pipeline?.job_id ? (
                <span className="crawler-debug-id">
                  子 Pipeline {run.pipeline.job_id}
                </span>
              ) : null}
            </div>
            {progress?.doc_id ? <p>当前文档：{progress.doc_id}</p> : null}
            {recentEvents.length > 0 ? (
              <ol className="crawler-event-list">
                {recentEvents.map((event) => (
                  <li
                    className={`crawler-event crawler-event-${event.level}`}
                    key={event.sequence}
                  >
                    <time>
                      {new Date(event.created_at).toLocaleTimeString("zh-CN", {
                        hour12: false,
                      })}
                    </time>
                    <span>{event.message}</span>
                    {event.doc_id ? <small>{event.doc_id}</small> : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p>等待后端产生阶段事件…</p>
            )}
          </section>
        ) : null}

        {status === "success" ? (
          <div className="crawler-result crawler-result-success">
            <CheckCircle2 size={18} />
            <div>
              <strong>采集任务完成</strong>
              <span>
                发现 {run?.items_found ?? 0} 篇 · 清洗{" "}
                {run?.items_promoted ?? 0} 篇 · 导入 {run?.items_imported ?? 0}{" "}
                篇
              </span>
              <span>
                Live 建图成功 {run?.items_pipeline_succeeded ?? 0} 篇 · 失败{" "}
                {run?.items_pipeline_failed ?? 0} 篇
              </span>
            </div>
          </div>
        ) : null}

        {status === "partial_success" ? (
          <div className="crawler-result crawler-result-partial" role="status">
            <AlertCircle size={18} />
            <div>
              <strong>采集任务部分成功</strong>
              {error ? <span>{error}</span> : null}
              {run?.filter_summary?.failed_documents.map((item) => (
                <span key={item.doc_id}>
                  {item.doc_id}：{item.message}
                </span>
              ))}
              {run?.artifact_path ? (
                <span>中间产物：{run.artifact_path}</span>
              ) : null}
            </div>
          </div>
        ) : null}

        {status === "failed" ? (
          <div className="crawler-result crawler-result-warning" role="alert">
            <AlertCircle size={16} />
            <span>{error ?? "采集任务失败"}</span>
          </div>
        ) : null}

        {sources === 0 ? (
          <div className="crawler-result crawler-result-warning">
            <AlertCircle size={16} /> 至少选择一个来源后才能开始采集。
          </div>
        ) : null}

        <div className="crawler-modal-footer">
          <div>
            <button
              className="crawler-secondary"
              type="button"
              disabled={isRunning || status === "submitting"}
              onClick={handleClose}
            >
              关闭
            </button>
            <button
              className="crawler-primary"
              type="button"
              disabled={
                !llmConfigured ||
                isRunning ||
                status === "submitting" ||
                sources === 0 ||
                limit < 1
              }
              onClick={handleRun}
            >
              <Search size={15} />
              {status === "success" ||
              status === "partial_success" ||
              status === "failed"
                ? "再次采集"
                : "开始采集"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
