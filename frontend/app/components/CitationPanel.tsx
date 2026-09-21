"use client";

type CitedEvidence = {
  source_index: string;
  source_id: string;
  byte_offset_start: number;
  byte_offset_end: number;
  excerpt: string;
};

export default function CitationPanel({ evidence }: { evidence: CitedEvidence[] }) {
  if (!evidence || evidence.length === 0) {
    return <p className="text-sm text-slate-400">No citations yet — run adjudication first.</p>;
  }

  return (
    <div className="card p-5">
      <h2 className="mb-3 text-sm font-semibold text-slate-800">Cited Evidence ({evidence.length})</h2>
      <ol className="space-y-3">
        {evidence.map((e, i) => (
          <li key={i} className="rounded-lg border border-slate-100 p-3">
            <div className="text-xs text-slate-400">
              {e.source_index} / {e.source_id} · bytes [{e.byte_offset_start}–{e.byte_offset_end}]
            </div>
            <blockquote className="mt-1.5 border-l-2 border-blue-400 pl-3 text-sm text-slate-700">
              {e.excerpt}
            </blockquote>
          </li>
        ))}
      </ol>
    </div>
  );
}
