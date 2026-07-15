import { useState, useEffect, useRef } from "react";
import { fetchEntitySearch } from "../api/client";
import type { GraphNode } from "../types";

interface SearchBarProps {
  onSelect: (nodeId: string) => void;
  onClear: () => void;
}

export default function SearchBar({ onSelect, onClear }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GraphNode[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (query.length < 1) {
      setResults([]);
      return;
    }
    timerRef.current = setTimeout(() => {
      setLoading(true);
      fetchEntitySearch(query)
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [query]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowResults(false);
      }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  return (
    <div ref={containerRef} style={{ position: "relative", flex: 1, maxWidth: 420 }}>
      <input
        type="text"
        value={query}
        onChange={(e) => {
          const value = e.target.value;
          setQuery(value);
          setShowResults(true);
          if (!value.trim()) onClear();
        }}
        placeholder="搜索实体并筛选一跳关系..."
        style={{
          width: "100%", padding: "8px 14px", background: "#ffffff",
          border: "1px solid #d7dfdd", borderRadius: 8, color: "#172026",
          fontSize: 14, outline: "none",
        }}
      />
      {showResults && results.length > 0 && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4,
          background: "#ffffff", border: "1px solid #d7dfdd", borderRadius: 8,
          maxHeight: 280, overflowY: "auto", boxShadow: "0 4px 12px rgba(0,0,0,0.1)", zIndex: 20,
        }}>
          {results.map((n) => (
            <div
              key={n.id}
              onClick={() => {
                onSelect(n.id);
                setShowResults(false);
                setQuery(n.name);
              }}
              style={{ padding: "10px 14px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #e2e8e6" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#f8faf9")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              <span style={{ fontWeight: 600, color: "#172026" }}>{n.name}</span>
              <span style={{ marginLeft: 8, fontSize: 11, color: "#64748b" }}>{n.type}</span>
            </div>
          ))}
        </div>
      )}
      {loading && <span style={{ position: "absolute", right: 12, top: 10, fontSize: 11, color: "#94a3b8" }}>搜索中...</span>}
    </div>
  );
}
