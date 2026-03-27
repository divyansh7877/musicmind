import { useQuery } from '@tanstack/react-query';
import { getActivity } from '../utils/api';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';

function timeAgo(timestamp: string): string {
  const seconds = Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

const TYPE_ICONS: Record<string, string> = {
  enrichment: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
  feedback: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  correction: 'M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7',
};

export default function ActivityPage() {
  const { isLoggedIn } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoggedIn) navigate('/login', { state: { from: '/activity' } });
  }, [isLoggedIn, navigate]);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['activity'],
    queryFn: () => getActivity(),
    enabled: isLoggedIn,
    refetchInterval: 30000,
  });

  return (
    <div className="max-w-2xl mx-auto px-6 py-12">
      <div className="flex items-center justify-between mb-8 animate-fade-up">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-3xl text-ink">Activity</h1>
          <p className="text-sm text-slate mt-1">Recent enrichments across MusicMind</p>
        </div>
        <button
          onClick={() => refetch()}
          className="text-xs text-ghost hover:text-amber transition-colors cursor-pointer font-[family-name:var(--font-mono)]"
        >
          Refresh
        </button>
      </div>

      {isLoading && (
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex gap-4 p-4 rounded-xl bg-cream animate-pulse">
              <div className="w-10 h-10 rounded-lg bg-mist/40" />
              <div className="flex-1 space-y-2">
                <div className="h-3 bg-mist/40 rounded w-3/4" />
                <div className="h-2 bg-mist/30 rounded w-1/2" />
              </div>
            </div>
          ))}
        </div>
      )}

      {isError && (
        <div className="text-center py-12 animate-fade-up">
          <p className="text-slate mb-2">Failed to load activity</p>
          <button
            onClick={() => refetch()}
            className="text-sm font-semibold text-amber hover:text-rust transition-colors cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {data && data.activities.length === 0 && (
        <div className="text-center py-16 animate-fade-up">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-paper-warm flex items-center justify-center">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-ghost">
              <path d={TYPE_ICONS.enrichment} />
            </svg>
          </div>
          <p className="text-slate">No activity yet</p>
          <p className="text-xs text-ghost mt-1">Search for a song to get started</p>
        </div>
      )}

      {data && data.activities.length > 0 && (
        <div className="space-y-2">
          {data.activities.map((activity, i) => (
            <div
              key={activity.id}
              className="flex items-start gap-4 p-4 rounded-xl bg-cream/60 hover:bg-cream border border-transparent hover:border-mist/40 transition-all animate-fade-up"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="w-10 h-10 rounded-lg bg-amber/10 flex items-center justify-center flex-shrink-0">
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-amber"
                >
                  <path d={TYPE_ICONS[activity.type] || TYPE_ICONS.enrichment} />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-ink">{activity.description}</p>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs text-ghost font-[family-name:var(--font-mono)]">
                    {timeAgo(activity.timestamp)}
                  </span>
                  {activity.metadata.song != null && (
                    <span className="text-xs text-amber font-medium">
                      {String(activity.metadata.song)}
                    </span>
                  )}
                  {activity.metadata.completeness !== undefined && (
                    <span className="text-xs text-ghost font-[family-name:var(--font-mono)]">
                      {Math.round((activity.metadata.completeness as number) * 100)}%
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {data && data.total > data.activities.length && (
        <div className="text-center mt-6">
          <span className="text-xs text-ghost">
            Showing {data.activities.length} of {data.total} activities
          </span>
        </div>
      )}
    </div>
  );
}
