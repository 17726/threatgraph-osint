import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d";

import { buildGraph3DData, type Graph3DLink, type Graph3DNode } from "../graphOptions";
import type { GraphEdge, GraphNode, GraphPayload } from "../types";

interface Graph3DProps {
  graph: GraphPayload;
  highlightNodeIds?: string[];
  searchNodeId?: string | null;
  focusNodeId?: string | null;
  focusEdgeId?: string | null;
  onNodeClick: (node: GraphNode) => void;
  onEdgeClick: (edge: GraphEdge) => void;
  onBackgroundClick?: () => void;
}

const MINIMUM_WIDTH = 320;
const MINIMUM_HEIGHT = 440;

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export default function Graph3D({
  graph,
  highlightNodeIds = [],
  searchNodeId = null,
  focusNodeId = null,
  focusEdgeId = null,
  onNodeClick,
  onEdgeClick,
  onBackgroundClick,
}: Graph3DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraphMethods<Graph3DNode, Graph3DLink> | undefined>(undefined);
  const [size, setSize] = useState({ width: MINIMUM_WIDTH, height: MINIMUM_HEIGHT });
  const graphData = useMemo(
    () => buildGraph3DData(graph, { highlightNodeIds, searchNodeId, focusNodeId, focusEdgeId }),
    [graph, highlightNodeIds, searchNodeId, focusNodeId, focusEdgeId],
  );
  const cameraDistance = Math.max(360, Math.round(Math.cbrt(graphData.nodes.length) * 100));

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const updateSize = () => {
      setSize({
        width: Math.max(container.clientWidth, MINIMUM_WIDTH),
        height: Math.max(container.clientHeight, MINIMUM_HEIGHT),
      });
    };
    updateSize();

    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(updateSize);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={containerRef} className="graph-3d" aria-label="三维关系图谱">
      <ForceGraph3D<Graph3DNode, Graph3DLink>
        ref={graphRef}
        graphData={graphData}
        width={size.width}
        height={size.height}
        backgroundColor="#ffffff"
        showNavInfo={false}
        nodeLabel={(node) =>
          `<strong>${escapeHtml(node.name)}</strong><br/>类型：${escapeHtml(node.type)}<br/>置信度：${node.confidence.toFixed(2)}`
        }
        nodeColor="color"
        nodeVal="val"
        nodeRelSize={3.5}
        nodeOpacity={0.92}
        nodeResolution={16}
        linkLabel={(link) =>
          `${escapeHtml(link.name)}<br/>置信度：${link._raw.confidence.toFixed(2)}`
        }
        linkColor="color"
        linkWidth="width"
        linkOpacity={0.78}
        linkDirectionalArrowLength={(link) => (link.width >= 3 ? 5 : 3)}
        linkDirectionalArrowRelPos={0.85}
        linkDirectionalArrowColor="color"
        linkDirectionalParticles="particles"
        linkDirectionalParticleColor="color"
        linkDirectionalParticleWidth={(link) => (link.width >= 3 ? 2.2 : 1)}
        linkDirectionalParticleSpeed={0.006}
        linkHoverPrecision={8}
        warmupTicks={80}
        cooldownTime={5000}
        onEngineStop={() =>
          graphRef.current?.cameraPosition(
            { x: 0, y: 0, z: cameraDistance },
            { x: 0, y: 0, z: 0 },
            600,
          )
        }
        onNodeClick={(node) => onNodeClick(node._raw)}
        onLinkClick={(link) => onEdgeClick(link._raw)}
        onBackgroundClick={onBackgroundClick}
      />
      <div className="graph-3d-hint" aria-hidden="true">
        拖拽旋转 · 滚轮缩放 · 单击查看详情
      </div>
    </div>
  );
}
