import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { searchSong } from '../utils/api';
import { useAuth } from '../hooks/useAuth';

const SUGGESTIONS = [
  'Bohemian Rhapsody',
  'Stairway to Heaven',
  'Hotel California',
  'Imagine',
  'Smells Like Teen Spirit',
  'Billie Jean',
];

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { isLoggedIn } = useAuth();

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const mutation = useMutation({
    mutationFn: searchSong,
    onSuccess: (data) => {
      if (data.graph_node_ids.length > 0) {
        navigate(`/graph/${data.graph_node_ids[0]}`, { state: { searchResult: data } });
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    if (!isLoggedIn) {
      navigate('/login', { state: { from: '/', query: trimmed } });
      return;
    }
    mutation.mutate(trimmed);
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-10rem)] px-6">
      <div className="w-full max-w-2xl animate-fade-up">
        <div className="text-center mb-12">
          <h1 className="font-[family-name:var(--font-display)] text-6xl md:text-7xl text-ink mb-4 leading-[1.1]">
            Discover the
            <br />
            <span className="text-amber italic">music graph</span>
          </h1>
          <p className="text-slate text-lg max-w-md mx-auto">
            Search any song to explore its connections across artists, albums,
            labels, and venues.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="relative group">
          <div className="absolute -inset-1 bg-gradient-to-r from-amber/20 via-rust/10 to-sage/20 rounded-2xl blur-lg opacity-0 group-focus-within:opacity-100 transition-opacity duration-500" />
          <div className="relative flex items-center bg-cream border border-mist rounded-xl shadow-sm focus-within:border-amber focus-within:shadow-lg focus-within:shadow-amber/5 transition-all duration-300">
            <svg
              className="ml-5 text-ghost flex-shrink-0"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search for a song..."
              maxLength={200}
              className="flex-1 bg-transparent px-4 py-5 text-lg text-ink placeholder:text-ghost focus:outline-none font-[family-name:var(--font-body)]"
              disabled={mutation.isPending}
            />
            <button
              type="submit"
              disabled={mutation.isPending || !query.trim()}
              className="mr-3 px-6 py-2.5 bg-ink text-cream rounded-lg text-sm font-semibold hover:bg-amber disabled:opacity-40 disabled:hover:bg-ink transition-colors cursor-pointer disabled:cursor-not-allowed"
            >
              {mutation.isPending ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Enriching
                </span>
              ) : (
                'Search'
              )}
            </button>
          </div>
        </form>

        {mutation.isError && (
          <div className="mt-6 p-4 bg-rust/5 border border-rust/20 rounded-xl animate-fade-in">
            <div className="flex items-start gap-3">
              <svg className="text-rust flex-shrink-0 mt-0.5" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="15" y1="9" x2="9" y2="15" />
                <line x1="9" y1="9" x2="15" y2="15" />
              </svg>
              <div>
                <p className="text-sm font-medium text-rust">Search failed</p>
                <p className="text-xs text-slate mt-1">
                  {(mutation.error as Error)?.message || 'Something went wrong. Please try again.'}
                </p>
                <button
                  onClick={() => mutation.mutate(query.trim())}
                  className="mt-2 text-xs font-semibold text-amber hover:text-rust transition-colors cursor-pointer"
                >
                  Retry
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="mt-10 flex flex-wrap justify-center gap-2">
          <span className="text-xs text-ghost mr-1 self-center">Try:</span>
          {SUGGESTIONS.map((s, i) => (
            <button
              key={s}
              onClick={() => { setQuery(s); inputRef.current?.focus(); }}
              className="px-3 py-1.5 text-xs rounded-full border border-mist/80 text-slate hover:border-amber hover:text-amber transition-all cursor-pointer animate-fade-up"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Decorative elements */}
      <div className="absolute top-32 left-12 w-64 h-64 bg-amber/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-24 right-16 w-48 h-48 bg-sage/5 rounded-full blur-3xl pointer-events-none" />
    </div>
  );
}
