import { Entity } from "../api/client";

const TYPE_COLORS: Record<string, string> = {
  PERSON: "bg-accent/20 text-accent",
  PHONE: "bg-warn/20 text-warn",
  VEHICLE: "bg-purple-400/20 text-purple-300",
  LOCATION: "bg-good/20 text-good",
  ORGANIZATION: "bg-pink-400/20 text-pink-300",
  FINANCIAL_ACCOUNT: "bg-alert/20 text-alert",
  EVENT: "bg-slate-400/20 text-slate-300",
  CASE: "bg-slate-400/20 text-slate-300",
};

export default function EntityPanel({ entity, onClose }: { entity: Entity | null; onClose: () => void }) {
  if (!entity) {
    return (
      <div className="card w-80 shrink-0 text-sm text-slate-400">
        Select a node on the graph to see its details, sources, and connections.
      </div>
    );
  }
  return (
    <div className="card w-80 shrink-0 flex flex-col gap-3">
      <div className="flex justify-between items-start">
        <div>
          <span className={`badge ${TYPE_COLORS[entity.type] ?? "bg-slate-400/20"}`}>{entity.type}</span>
          <h3 className="text-lg font-semibold mt-2 break-words">{entity.label}</h3>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-200">
          ✕
        </button>
      </div>
      <div className="text-xs text-slate-400">
        ID: <span className="text-slate-300 font-mono">{entity.id}</span>
      </div>
      <div className="text-xs text-slate-400">
        Corroborated by <span className="text-slate-200">{entity.source_count}</span> source document(s)
      </div>
      {Object.keys(entity.attributes).length > 0 && (
        <div className="border-t border-border pt-3 space-y-1">
          {Object.entries(entity.attributes).map(([k, v]) =>
            v ? (
              <div key={k} className="text-xs">
                <span className="text-slate-500 capitalize">{k.replace(/_/g, " ")}: </span>
                <span className="text-slate-200">{String(v)}</span>
              </div>
            ) : null
          )}
        </div>
      )}
    </div>
  );
}
