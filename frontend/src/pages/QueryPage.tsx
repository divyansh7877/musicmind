import { useState, useRef, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import { queryGraph } from '../utils/api';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import type { NLQueryResponse } from '../types/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  data?: unknown[];
}

const EXAMPLE_QUESTIONS = [
  'What artists are in the graph?',
  'Show me all songs by Radiohead',
  'Which albums have been enriched?',
  'Find songs similar to Bohemian Rhapsody',
];

export default function QueryPage() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { isLoggedIn } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const mutation = useMutation({
    mutationFn: queryGraph,
    onSuccess: (data: NLQueryResponse) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.answer, data: data.data },
      ]);
    },
    onError: (error: Error) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${error.message || 'Something went wrong.'}` },
      ]);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;
    if (!isLoggedIn) {
      navigate('/login', { state: { from: '/query' } });
      return;
    }
    setMessages((prev) => [...prev, { role: 'user', content: trimmed }]);
    setInput('');
    mutation.mutate(trimmed);
  };

  const handleExample = (q: string) => {
    setInput(q);
    inputRef.current?.focus();
  };

  return (
    <div className="flex flex-col h-[calc(100vh-10rem)]">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.length === 0 && (
            <div className="text-center py-16 animate-fade-up">
              <h1 className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-ink mb-4">
                Ask the <span className="text-amber italic">graph</span>
              </h1>
              <p className="text-slate text-base max-w-md mx-auto mb-8">
                Query the music knowledge graph in plain English. Ask about artists, songs, albums, and their connections.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {EXAMPLE_QUESTIONS.map((q, i) => (
                  <button
                    key={q}
                    onClick={() => handleExample(q)}
                    className="px-4 py-2 text-sm rounded-full border border-mist/80 text-slate hover:border-amber hover:text-amber transition-all cursor-pointer animate-fade-up"
                    style={{ animationDelay: `${i * 80}ms` }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-5 py-3 ${
                  msg.role === 'user'
                    ? 'bg-ink text-cream'
                    : 'bg-paper-warm border border-mist/60 text-ink'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                {msg.data && msg.data.length > 0 && (
                  <details className="mt-3">
                    <summary className="text-xs text-ghost cursor-pointer hover:text-amber transition-colors">
                      Raw data ({msg.data.length} results)
                    </summary>
                    <pre className="mt-2 text-xs bg-cream/50 rounded-lg p-3 overflow-x-auto max-h-48 font-[family-name:var(--font-mono)]">
                      {JSON.stringify(msg.data, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            </div>
          ))}

          {mutation.isPending && (
            <div className="flex justify-start animate-fade-in">
              <div className="bg-paper-warm border border-mist/60 rounded-2xl px-5 py-3">
                <div className="flex items-center gap-2 text-sm text-slate">
                  <svg className="animate-spin h-4 w-4 text-amber" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Querying the graph...
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input bar */}
      <div className="border-t border-mist/40 bg-cream/60 backdrop-blur-sm px-6 py-4">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div className="relative flex items-center bg-cream border border-mist rounded-xl shadow-sm focus-within:border-amber focus-within:shadow-lg focus-within:shadow-amber/5 transition-all duration-300">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question about the music graph..."
              maxLength={500}
              className="flex-1 bg-transparent px-5 py-4 text-sm text-ink placeholder:text-ghost focus:outline-none font-[family-name:var(--font-body)]"
              disabled={mutation.isPending}
            />
            <button
              type="submit"
              disabled={mutation.isPending || !input.trim()}
              className="mr-3 px-5 py-2 bg-ink text-cream rounded-lg text-sm font-semibold hover:bg-amber disabled:opacity-40 disabled:hover:bg-ink transition-colors cursor-pointer disabled:cursor-not-allowed"
            >
              Ask
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
