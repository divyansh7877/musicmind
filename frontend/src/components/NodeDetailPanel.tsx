import { useState } from 'react';
import type { GraphNode } from '../types/api';

interface Props {
  node: GraphNode;
  onClose: () => void;
  onFeedback: (type: string, value: number, comment?: string) => void;
  feedbackPending: boolean;
  feedbackSuccess: boolean;
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(', ');
  if (typeof value === 'object' && value !== null) return JSON.stringify(value, null, 1);
  return String(value ?? '—');
}

const NODE_COLORS: Record<string, string> = {
  Song: '#c2703e',
  Artist: '#8b3a1e',
  Album: '#6b7c5e',
  RecordLabel: '#7c6b5e',
  Instrument: '#5e6b7c',
  Venue: '#7c5e6b',
  Concert: '#5e7c6b',
};

export default function NodeDetailPanel({ node, onClose, onFeedback, feedbackPending, feedbackSuccess }: Props) {
  const [showCorrection, setShowCorrection] = useState(false);
  const [correctionComment, setCorrectionComment] = useState('');
  const [showReport, setShowReport] = useState(false);
  const [reportComment, setReportComment] = useState('');

  const color = NODE_COLORS[node.type] || '#c2703e';
  const label = (node.data.title || node.data.name || node.type) as string;
  const completeness = node.data.completeness_score as number | undefined;

  const hiddenKeys = new Set(['type', 'completeness_score', 'last_enriched', 'data_sources']);
  const dataEntries: Array<[string, string]> = Object.entries(node.data)
    .filter(([k]) => !hiddenKeys.has(k))
    .map(([k, v]) => [k, formatValue(v)]);

  return (
    <div className="absolute top-0 right-0 w-96 h-full bg-cream border-l border-mist/60 shadow-2xl shadow-ink/5 overflow-y-auto animate-slide-in z-20">
      {/* Header */}
      <div className="sticky top-0 bg-cream/95 backdrop-blur-sm border-b border-mist/40 p-4 flex items-start justify-between">
        <div className="flex items-start gap-3 min-w-0">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center text-cream font-semibold text-sm flex-shrink-0 font-[family-name:var(--font-mono)]"
            style={{ backgroundColor: color }}
          >
            {node.type.charAt(0)}
          </div>
          <div className="min-w-0">
            <p className="text-xs text-ghost uppercase tracking-wider font-medium">{node.type}</p>
            <h3 className="font-[family-name:var(--font-display)] text-lg text-ink leading-snug truncate">
              {label}
            </h3>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-ghost hover:text-ink p-1 rounded-lg hover:bg-paper-warm transition-colors cursor-pointer flex-shrink-0"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div className="p-4 space-y-5">
        {/* Completeness */}
        {completeness !== undefined && (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-ghost uppercase tracking-wider font-medium">Completeness</span>
              <span className="text-xs font-[family-name:var(--font-mono)] text-amber font-semibold">
                {Math.round(completeness * 100)}%
              </span>
            </div>
            <div className="h-1.5 bg-mist/40 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${completeness * 100}%`, backgroundColor: color }}
              />
            </div>
          </div>
        )}

        {/* Data fields */}
        <div>
          <h4 className="text-xs text-ghost uppercase tracking-wider font-medium mb-3">Properties</h4>
          <div className="space-y-2">
            {dataEntries.map(([key, display]) => (
              <div key={key} className="flex items-start gap-2 text-sm">
                <span className="text-ghost font-[family-name:var(--font-mono)] text-xs mt-0.5 w-28 flex-shrink-0 truncate">
                  {key}
                </span>
                <span className="text-ink text-xs break-all">{display}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Data sources */}
        {Array.isArray(node.data.data_sources) && node.data.data_sources.length > 0 && (
          <div>
            <h4 className="text-xs text-ghost uppercase tracking-wider font-medium mb-2">Sources</h4>
            <div className="flex flex-wrap gap-1.5">
              {(node.data.data_sources as string[]).map((src: string) => (
                <span
                  key={src}
                  className="px-2 py-0.5 rounded-md bg-paper-warm text-xs text-slate font-[family-name:var(--font-mono)]"
                >
                  {src}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Feedback section */}
        <div className="border-t border-mist/40 pt-4">
          <h4 className="text-xs text-ghost uppercase tracking-wider font-medium mb-3">Feedback</h4>

          {feedbackSuccess && (
            <div className="mb-3 p-2.5 bg-sage/10 border border-sage/20 rounded-lg text-xs text-sage font-medium animate-fade-in">
              Feedback submitted. Thank you!
            </div>
          )}

          <div className="flex items-center gap-2 mb-3">
            <button
              onClick={() => onFeedback('like', 1)}
              disabled={feedbackPending}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border border-mist/60 text-xs font-medium text-slate hover:border-sage hover:text-sage hover:bg-sage/5 transition-all cursor-pointer disabled:opacity-50"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M7 10v12" /><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z" />
              </svg>
              Accurate
            </button>
            <button
              onClick={() => onFeedback('dislike', -1)}
              disabled={feedbackPending}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border border-mist/60 text-xs font-medium text-slate hover:border-rust hover:text-rust hover:bg-rust/5 transition-all cursor-pointer disabled:opacity-50"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 14V2" /><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z" />
              </svg>
              Inaccurate
            </button>
          </div>

          {/* Correction */}
          <button
            onClick={() => setShowCorrection(!showCorrection)}
            className="w-full text-left px-3 py-2 text-xs text-slate hover:text-amber hover:bg-amber/5 rounded-lg transition-all cursor-pointer"
          >
            Suggest a correction
          </button>
          {showCorrection && (
            <div className="mt-2 space-y-2 animate-fade-in">
              <textarea
                value={correctionComment}
                onChange={(e) => setCorrectionComment(e.target.value)}
                placeholder="What should be corrected?"
                className="w-full p-3 rounded-lg border border-mist text-xs text-ink bg-paper placeholder:text-ghost focus:outline-none focus:border-amber resize-none"
                rows={3}
              />
              <button
                onClick={() => { onFeedback('correction', 0, correctionComment); setCorrectionComment(''); setShowCorrection(false); }}
                disabled={!correctionComment.trim() || feedbackPending}
                className="px-4 py-1.5 bg-ink text-cream text-xs rounded-lg font-medium hover:bg-amber disabled:opacity-40 transition-colors cursor-pointer disabled:cursor-not-allowed"
              >
                Submit correction
              </button>
            </div>
          )}

          {/* Report */}
          <button
            onClick={() => setShowReport(!showReport)}
            className="w-full text-left px-3 py-2 text-xs text-slate hover:text-rust hover:bg-rust/5 rounded-lg transition-all cursor-pointer"
          >
            Report an issue
          </button>
          {showReport && (
            <div className="mt-2 space-y-2 animate-fade-in">
              <textarea
                value={reportComment}
                onChange={(e) => setReportComment(e.target.value)}
                placeholder="Describe the issue..."
                className="w-full p-3 rounded-lg border border-mist text-xs text-ink bg-paper placeholder:text-ghost focus:outline-none focus:border-rust resize-none"
                rows={3}
              />
              <button
                onClick={() => { onFeedback('report', -1, reportComment); setReportComment(''); setShowReport(false); }}
                disabled={!reportComment.trim() || feedbackPending}
                className="px-4 py-1.5 bg-rust text-cream text-xs rounded-lg font-medium hover:bg-ink disabled:opacity-40 transition-colors cursor-pointer disabled:cursor-not-allowed"
              >
                Submit report
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
