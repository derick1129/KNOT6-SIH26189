import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { Entity, GraphData, Relation } from "../api/client";

const TYPE_COLOR: Record<string, string> = {
  PERSON: "#38bdf8",
  PHONE: "#fbbf24",
  VEHICLE: "#c084fc",
  LOCATION: "#34d399",
  ORGANIZATION: "#f472b6",
  FINANCIAL_ACCOUNT: "#f87171",
  EVENT: "#94a3b8",
  CASE: "#94a3b8",
};

interface Props {
  data: GraphData;
  highlightIds?: Set<string>;
  onNodeClick?: (entity: Entity) => void;
  height?: number;
}

export default function GraphView({ data, highlightIds, onNodeClick, height = 560 }: Props) {
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const graphData = useMemo(() => {
    const nodes = data.nodes.map((n) => ({ ...n, val: 1 + Math.min(n.source_count, 6) }));
    const links = data.edges.map((e: Relation) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: e.type,
      weight: e.weight,
    }));
    return { nodes, links };
  }, [data]);

  return (
    <div ref={containerRef} className="card p-0 overflow-hidden" style={{ height }}>
      {width > 0 && (
        <ForceGraph2D
          ref={fgRef}
          graphData={graphData as any}
          backgroundColor="#111a2e"
          nodeLabel={(n: any) => `${n.label} (${n.type})`}
          nodeColor={(n: any) =>
            highlightIds && highlightIds.size > 0 && !highlightIds.has(n.id)
              ? "#334155"
              : TYPE_COLOR[n.type] ?? "#94a3b8"
          }
          nodeRelSize={4}
          linkColor={() => "rgba(148,163,184,0.35)"}
          linkWidth={(l: any) => Math.min(1 + (l.weight ?? 1) * 0.4, 5)}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkLabel={(l: any) => l.type}
          onNodeClick={(n: any) => onNodeClick?.(n)}
          cooldownTicks={80}
          width={width}
          height={height}
        />
      )}
    </div>
  );
}
