import { FileText, Upload, X, Loader2, CheckCircle2, AlertCircle, BookOpen } from "lucide-react";
import { useState, useRef } from "react";
import { runPipeline, type PipelineResult } from "../api/client";

interface PipelineModalProps {
  open: boolean;
  onClose: () => void;
  /** 成功后自动刷新图谱 */
  onSuccess: () => void;
}

type Status = "idle" | "uploading" | "success" | "error";

export default function PipelineModal({ open, onClose, onSuccess }: PipelineModalProps) {
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!open) return null;

  const handleRun = async () => {
    if (!documentFile) return;
    setStatus("uploading");
    setErrorMsg("");

    try {
      const res = await runPipeline(documentFile);
      setResult(res);
      setStatus("success");
      onSuccess();
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "导入失败");
      setStatus("error");
    }
  };

  const resetFiles = () => {
    setDocumentFile(null);
    setStatus("idle");
    setResult(null);
    setErrorMsg("");
  };

  const handleClose = () => {
    resetFiles();
    onClose();
  };

  return (
    <div
      onClick={handleClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff", borderRadius: 12, padding: 24, width: 520,
          maxWidth: "90vw", boxShadow: "0 8px 32px rgba(0,0,0,0.15)",
        }}
      >
        {/* 标题行 */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <BookOpen size={18} color="#0f766e" />
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#172026" }}>导入情报文档</h2>
          </div>
          <button onClick={handleClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#64748b", padding: 4 }}>
            <X size={18} />
          </button>
        </div>

        <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 16px", lineHeight: 1.5 }}>
          上传一篇原始情报文档（JSON 格式），后端自动完成 LLM 抽取 → 实体/关系归一化 → 写入知识库。成功后图谱即刻展示新数据。
        </p>

        {/* 文件选择 */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>文档文件</label>
          <div
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${documentFile ? "#0f766e" : "#d1d5db"}`,
              borderRadius: 8, padding: 20,
              textAlign: "center", cursor: "pointer",
              background: documentFile ? "#f0fdf4" : "#f9fafb",
              transition: "all 0.15s",
            }}
          >
            {documentFile ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, fontSize: 13 }}>
                <FileText size={16} color="#0f766e" />
                <span style={{ color: "#166534", fontWeight: 500 }}>{documentFile.name}</span>
                <span style={{ color: "#9ca3af", fontSize: 11 }}>({(documentFile.size / 1024).toFixed(1)} KB)</span>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, color: "#9ca3af" }}>
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
            onChange={(e) => setDocumentFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {/* 成功提示 */}
        {status === "success" && result && (
          <div style={{
            padding: 14, borderRadius: 8, background: "#f0fdf4",
            border: "1px solid #bbf7d0",
            marginBottom: 16, fontSize: 12,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "#166534", fontWeight: 600, marginBottom: 10 }}>
              <CheckCircle2 size={16} /> Pipeline 运行成功
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", color: "#374151" }}>
              <span>正式实体: <strong>{result.canonical_entities}</strong></span>
              <span>正式关系: <strong>{result.canonical_relations}</strong></span>
              <span>证据: <strong>{result.evidence}</strong></span>
              <span>行为模式: <strong>{result.behavior_patterns}</strong></span>
              <span>候选实体: <strong>{result.extracted_entities}</strong></span>
              <span>候选关系: <strong>{result.extracted_relations}</strong></span>
            </div>
          </div>
        )}

        {/* 错误提示 */}
        {status === "error" && (
          <div style={{
            padding: 12, borderRadius: 8, background: "#fef2f2",
            border: "1px solid #fecaca",
            marginBottom: 16, fontSize: 12, color: "#991b1b",
            display: "flex", alignItems: "center", gap: 6,
          }}>
            <AlertCircle size={16} /> {errorMsg}
          </div>
        )}

        {/* 按钮行 */}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            onClick={handleClose}
            style={{
              padding: "8px 16px", borderRadius: 8, border: "1px solid #d1d5db",
              background: "#fff", cursor: "pointer", fontSize: 13, color: "#374151",
            }}
          >
            关闭
          </button>
          <button
            onClick={handleRun}
            disabled={!documentFile || status === "uploading"}
            style={{
              padding: "8px 16px", borderRadius: 8, border: "none",
              background: !documentFile ? "#d1d5db" : "#0f766e",
              color: !documentFile ? "#9ca3af" : "#fff",
              cursor: !documentFile ? "not-allowed" : "pointer",
              fontSize: 13, fontWeight: 600,
              display: "flex", alignItems: "center", gap: 6,
            }}
          >
            {status === "uploading" ? (
              <>
                <Loader2 size={14} className="loader-spin" />
                运行中...
              </>
            ) : (
              "导入并处理"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
