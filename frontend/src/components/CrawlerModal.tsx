import {
  AlertCircle,
  CheckCircle2,
  Filter,
  Loader2,
  Search,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

type CrawlerModalProps = {
  open: boolean;
  target: string;
  onClose: () => void;
  onSuccess: () => void;
};

type DemoStatus = "idle" | "running" | "success";

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

const STAGES = ["正在发现来源", "正在清洗文档", "正在导入图谱"];

export default function CrawlerModal({
  open,
  target,
  onClose,
  onSuccess,
}: CrawlerModalProps) {
  const [selectedTarget, setSelectedTarget] = useState(target);
  const [limit, setLimit] = useState(5);
  const [selectedSources, setSelectedSources] = useState<number[]>([0]);
  const [filter, setFilter] = useState(false);
  const [status, setStatus] = useState<DemoStatus>("idle");
  const [stage, setStage] = useState(0);
  const timersRef = useRef<number[]>([]);

  const sources = useMemo(
    () => selectedSources.reduce((mask, index) => mask | (1 << index), 0),
    [selectedSources],
  );
  const isRunning = status === "running";

  useEffect(() => {
    if (open) {
      setSelectedTarget(target);
      setStatus("idle");
      setStage(0);
    }
    return () => {
      timersRef.current.forEach((timer) => window.clearTimeout(timer));
      timersRef.current = [];
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

  const handleRun = () => {
    if (isRunning || sources === 0 || limit < 1) return;
    setStatus("running");
    setStage(0);
    timersRef.current = [
      window.setTimeout(() => setStage(1), 1200),
      window.setTimeout(() => setStage(2), 2400),
      window.setTimeout(() => {
        setStatus("success");
        onSuccess();
      }, 3600),
    ];
  };

  const handleClose = () => {
    if (isRunning) return;
    onClose();
  };

  return (
    <div className="crawler-modal-backdrop" onClick={handleClose}>
      <section
        aria-label="采集情报弹窗"
        className="crawler-modal"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="crawler-modal-header">
          <div>
            <h2>采集情报</h2>
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

        <div className="crawler-form-grid">
          <label className="crawler-field">
            <span>目标组织</span>
            <select
              aria-label="目标组织"
              value={selectedTarget}
              disabled={isRunning}
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
              disabled={isRunning}
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
                  disabled={isRunning}
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
            disabled={isRunning}
            onChange={(event) => setFilter(event.target.checked)}
          />
          <Filter size={16} />
          <span>
            <strong>启用 LLM 相关性过滤</strong>
          </span>
        </label>

        {isRunning ? (
          <div className="crawler-progress" role="status">
            <div className="crawler-progress-title">
              <Loader2 size={16} className="loader-spin" />
              <strong>{STAGES[stage]}</strong>
              <span>{stage + 1}/3</span>
            </div>
            <div className="crawler-progress-track">
              <div style={{ width: `${((stage + 1) / 3) * 100}%` }} />
            </div>
            <p>任务正在本地模拟，暂不调用后端采集接口。</p>
          </div>
        ) : null}

        {status === "success" ? (
          <div className="crawler-result crawler-result-success">
            <CheckCircle2 size={18} />
            <div>
              <strong>采集任务完成</strong>
              <span>发现 12 篇 · 清洗 10 篇 · 导入 8 篇</span>
            </div>
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
              disabled={isRunning}
              onClick={handleClose}
            >
              关闭
            </button>
            <button
              className="crawler-primary"
              type="button"
              disabled={isRunning || sources === 0 || limit < 1}
              onClick={handleRun}
            >
              <Search size={15} />
              {status === "success" ? "再次演示" : "开始采集"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
