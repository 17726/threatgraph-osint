import { useState, useEffect, useRef } from "react";

interface SearchBarProps {
  nodes: { id: string; name: string; type: string; aliases: string[] }[];
  onSelect: (nodeId: string) => void;
}

export default function SearchBar({ nodes, onSelect }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [showResults, setShowResults] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const results =
    query.length < 1
      ? []
      : nodes
          .filter((n) => {
            const q = query.toLowerCase();
            const matchName = n.name?.toLowerCase().includes(q) ?? false;
            const matchAlias = n.aliases?.some((a) => a?.toLowerCase().includes(q)) ?? false;
            const matchType = n.type?.toLowerCase().includes(q) ?? false;
            return matchName || matchAlias || matchType;
          })
          .slice(0, 8);

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
          setQuery(e.target.value);
          setShowResults(true);
        }}
        placeholder="搜索实体..."
        style={{
          width: "100%",
          padding: "8px 14px",
          background: "#ffffff",
          border: "1px solid #d7dfdd",
          borderRadius: 8,
          color: "#172026",
          fontSize: 14,
          outline: "none",
        }}
      />
      {showResults && results.length > 0 && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            marginTop: 4,
            background: "#ffffff",
            border: "1px solid #d7dfdd",
            borderRadius: 8,
            maxHeight: 280,
            overflowY: "auto",
            boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
            zIndex: 20,
          }}
        >
          {results.map((n) => (
            <div
              key={n.id}
              onClick={() => {
                onSelect(n.id);
                setShowResults(false);
                setQuery("");
              }}
              style={{
                padding: "10px 14px",
                cursor: "pointer",
                fontSize: 13,
                borderBottom: "1px solid #e2e8e6",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#f8faf9")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              <span style={{ fontWeight: 600, color: "#172026" }}>{n.name}</span>
              <span style={{ marginLeft: 8, fontSize: 11, color: "#64748b" }}>{n.type}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
