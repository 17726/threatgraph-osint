import { FileText, Upload, X, Loader2, CheckCircle2, AlertCircle, BookOpen } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { runPipeline, type ExtractionMode, type PipelineResult } from "../api/client";

interface PipelineModalProps {
  open: boolean;
  onClose: () => void;
  /** 成功后自动刷新图谱 */
  onSuccess: () => void;
}

type Status = "idle" | "importing" | "pending" | "running" | "success" | "error";

const STATUS_LABELS: Record<Exclude<Status, "idle" | "success" | "error">, string> = {
  importing: "正在校验并导入标准文档...",
  pending: "任务已提交，等待后台执行...",
  running: "正在抽取实体关系并更新图谱...",
};

export default function PipelineModal({ open, onClose, onSuccess }: PipelineModalProps) {
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [extractionMode, setExtractionMode] = useState<ExtractionMode>("reviewed");
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  if (!open) return null;

  const handleRun = async () => {
    if (!documentFile) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus("importing");
    setErrorMsg("");

    try {
      const res = await runPipeline(documentFile, {
        extractionMode,
        signal: controller.signal,
        onStatus: setStatus,
      });
      setResult(res);
      setStatus("success");
      onSuccess();
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setErrorMsg(e instanceof Error ? e.message : "导入失败");
      setStatus("error");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  };

  const resetFiles = () => {
    setDocumentFile(null);
    setStatus("idle");
    setResult(null);
    setErrorMsg("");
  };

  const handleClose = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    resetFiles();
    onClose();
  };

  const isProcessing = ["importing", "pending", "running"].includes(status);
  const actionDisabled = !documentFile || isProcessing;

  return (
    <div
      onClick={handleClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          borderRadius: 12,
          padding: 24,
          width: 520,
          maxWidth: "90vw",
          boxShadow: "0 8px 32px rgba(0,0,0,0.15)",
        }}
      >
        {/* 标题行 */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 20,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <BookOpen size={18} color="#0f766e" />
            <h2
              style={{
                margin: 0,
                fontSize: 16,
                fontWeight: 700,
                color: "#172026",
              }}
            >
              导入并分析情报文档
            </h2>
          </div>
          <button
            aria-label="关闭"
            onClick={handleClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "#64748b",
              padding: 4,
            }}
          >
            <X size={18} />
          </button>
        </div>

        <p
          style={{
            fontSize: 12,
            color: "#64748b",
            margin: "0 0 16px",
            lineHeight: 1.5,
          }}
        >
          上传一篇已完成采集、清洗和相关性判断的标准
          document.json。后端会显式执行抽取、契约校验、归一化和 SQLite
          建图；采集与清洗脚本不在浏览器中伪执行。
        </p>

        {/* 文件选择 */}
        <div style={{ marginBottom: 24 }}>
          <label
            style={{
              display: "block",
              fontSize: 12,
              fontWeight: 600,
              color: "#475569",
              marginBottom: 6,
            }}
          >
            文档文件
          </label>
          <div
            aria-disabled={isProcessing}
            onClick={() => {
              if (!isProcessing) fileInputRef.current?.click();
            }}
            style={{
              border: `2px dashed ${documentFile ? "#0f766e" : "#d1d5db"}`,
              borderRadius: 8,
              padding: 20,
              textAlign: "center",
              cursor: isProcessing ? "not-allowed" : "pointer",
              background: documentFile ? "#f0fdf4" : "#f9fafb",
              transition: "all 0.15s",
            }}
          >
            {documentFile ? (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                  fontSize: 13,
                }}
              >
                <FileText size={16} color="#0f766e" />
                <span style={{ color: "#166534", fontWeight: 500 }}>{documentFile.name}</span>
                <span style={{ color: "#9ca3af", fontSize: 11 }}>
                  ({(documentFile.size / 1024).toFixed(1)} KB)
                </span>
              </div>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 6,
                  color: "#9ca3af",
                }}
              >
                <Upload size={22} />
                <span style={{ fontSize: 13 }}>选择 JSON 文档</span>
                <span style={{ fontSize: 11 }}>支持 document.json 格式</span>
              </div>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            hidden
            disabled={isProcessing}
            onChange={(e) => setDocumentFile(e.target.files?.[0] ?? null)}
          />
        </div>

        <fieldset style={{ border: 0, padding: 0, margin: "0 0 20px" }}>
          <legend
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "#475569",
              marginBottom: 8,
            }}
          >
            抽取方式
          </legend>
          <label
            style={{
              display: "flex",
              gap: 8,
              alignItems: "flex-start",
              marginBottom: 8,
              cursor: "pointer",
            }}
          >
            <input
              type="radio"
              name="extraction-mode"
              value="reviewed"
              checked={extractionMode === "reviewed"}
              disabled={isProcessing}
              onChange={() => setExtractionMode("reviewed")}
            />
            <span style={{ fontSize: 12, color: "#374151", lineHeight: 1.45 }}>
              <strong>已审核结果（演示推荐）</strong>
              <br />
              复用仓库中的已审核 extraction_result，不调用外部模型，结果稳定。
            </span>
          </label>
          <label
            style={{
              display: "flex",
              gap: 8,
              alignItems: "flex-start",
              cursor: "pointer",
            }}
          >
            <input
              type="radio"
              name="extraction-mode"
              value="live"
              checked={extractionMode === "live"}
              disabled={isProcessing}
              onChange={() => setExtractionMode("live")}
            />
            <span style={{ fontSize: 12, color: "#374151", lineHeight: 1.45 }}>
              <strong>现场 LLM 抽取</strong>
              <br />
              显式调用后端配置的模型，耗时、费用和输出会受外部服务影响。
            </span>
          </label>
        </fieldset>

        {isProcessing && (
          <div
            style={{
              padding: 12,
              borderRadius: 8,
              background: "#eff6ff",
              border: "1px solid #bfdbfe",
              marginBottom: 16,
              fontSize: 12,
              color: "#1d4ed8",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <Loader2 size={15} className="loader-spin" />
            {STATUS_LABELS[status as "importing" | "pending" | "running"]}
          </div>
        )}

        {/* 成功提示 */}
        {status === "success" && result && (
          <div
            style={{
              padding: 14,
              borderRadius: 8,
              background: "#f0fdf4",
              border: "1px solid #bbf7d0",
              marginBottom: 16,
              fontSize: 12,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                color: "#166534",
                fontWeight: 600,
                marginBottom: 10,
              }}
            >
              <CheckCircle2 size={16} /> Pipeline 运行成功
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "4px 16px",
                color: "#374151",
              }}
            >
              <span>
                正式实体: <strong>{result.canonical_entities ?? 0}</strong>
              </span>
              <span>
                正式关系: <strong>{result.canonical_relations ?? 0}</strong>
              </span>
              <span>
                证据: <strong>{result.evidence ?? 0}</strong>
              </span>
              <span>
                行为模式: <strong>{result.behavior_patterns ?? 0}</strong>
              </span>
              <span>
                候选实体: <strong>{result.extracted_entities ?? 0}</strong>
              </span>
              <span>
                候选关系: <strong>{result.extracted_relations ?? 0}</strong>
              </span>
            </div>
          </div>
        )}

        {/* 错误提示 */}
        {status === "error" && (
          <div
            style={{
              padding: 12,
              borderRadius: 8,
              background: "#fef2f2",
              border: "1px solid #fecaca",
              marginBottom: 16,
              fontSize: 12,
              color: "#991b1b",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <AlertCircle size={16} /> {errorMsg}
          </div>
        )}

        {/* 按钮行 */}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            onClick={handleClose}
            style={{
              padding: "8px 16px",
              borderRadius: 8,
              border: "1px solid #d1d5db",
              background: "#fff",
              cursor: "pointer",
              fontSize: 13,
              color: "#374151",
            }}
          >
            关闭
          </button>
          <button
            onClick={handleRun}
            disabled={actionDisabled}
            style={{
              padding: "8px 16px",
              borderRadius: 8,
              border: "none",
              background: actionDisabled ? "#d1d5db" : "#0f766e",
              color: actionDisabled ? "#9ca3af" : "#fff",
              cursor: actionDisabled ? "not-allowed" : "pointer",
              fontSize: 13,
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            {isProcessing ? (
              <>
                <Loader2 size={14} className="loader-spin" />
                运行中...
              </>
            ) : extractionMode === "live" ? (
              "导入并现场抽取"
            ) : (
              "导入并处理"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
