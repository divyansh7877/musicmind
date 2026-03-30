import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { UserButton } from '@clerk/react';

const navLinks = [
  { to: '/', label: 'Search' },
  { to: '/query', label: 'Ask' },
  { to: '/activity', label: 'Activity' },
];

export default function Layout() {
  const { isLoggedIn, user, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="min-h-screen flex flex-col">
      <div className="noise-overlay" />

      <header className="border-b border-mist/60 bg-cream/80 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-8 h-8 rounded-full bg-amber flex items-center justify-center">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </div>
            <span className="font-[family-name:var(--font-display)] text-xl tracking-tight text-ink group-hover:text-amber transition-colors">
              MusicMind
            </span>
          </Link>

          <nav className="flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  location.pathname === link.to
                    ? 'bg-ink text-cream'
                    : 'text-slate hover:bg-paper-warm hover:text-ink'
                }`}
              >
                {link.label}
              </Link>
            ))}

            <div className="w-px h-6 bg-mist mx-2" />

            {isLoggedIn ? (
              <div className="flex items-center gap-3">
                <span className="text-sm text-slate font-medium">
                  {user?.username}
                </span>
                <UserButton
                  afterSignOutUrl="/login"
                  userProfileUrl="/profile"
                />
              </div>
            ) : (
              <Link
                to="/login"
                className="px-4 py-2 rounded-lg text-sm font-medium bg-amber text-cream hover:bg-rust transition-colors"
              >
                Sign in
              </Link>
            )}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-mist/40 py-6">
        <div className="max-w-7xl mx-auto px-6 flex items-center justify-between text-xs text-ghost">
          <span>MusicMind &mdash; Music Knowledge Graph</span>
          <span className="font-[family-name:var(--font-mono)]">v1.0</span>
        </div>
      </footer>
    </div>
  );
}
