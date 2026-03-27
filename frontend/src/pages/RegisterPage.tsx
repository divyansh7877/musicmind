import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function RegisterPage() {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);
    try {
      await register(username, password, email);
      navigate('/', { replace: true });
    } catch (err) {
      setError((err as Error).message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center px-6">
      <div className="w-full max-w-sm animate-fade-up">
        <div className="text-center mb-8">
          <h1 className="font-[family-name:var(--font-display)] text-4xl text-ink mb-2">
            Create account
          </h1>
          <p className="text-sm text-slate">Join MusicMind to explore music connections</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 bg-rust/5 border border-rust/20 rounded-lg text-xs text-rust animate-fade-in">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="username" className="block text-xs text-ghost uppercase tracking-wider font-medium mb-1.5">
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              minLength={3}
              className="w-full px-4 py-3 rounded-lg border border-mist bg-cream text-sm text-ink placeholder:text-ghost focus:outline-none focus:border-amber transition-colors"
              placeholder="Choose a username"
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-xs text-ghost uppercase tracking-wider font-medium mb-1.5">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-3 rounded-lg border border-mist bg-cream text-sm text-ink placeholder:text-ghost focus:outline-none focus:border-amber transition-colors"
              placeholder="your@email.com"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-xs text-ghost uppercase tracking-wider font-medium mb-1.5">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className="w-full px-4 py-3 rounded-lg border border-mist bg-cream text-sm text-ink placeholder:text-ghost focus:outline-none focus:border-amber transition-colors"
              placeholder="Min 8 characters"
            />
          </div>

          <div>
            <label htmlFor="confirmPassword" className="block text-xs text-ghost uppercase tracking-wider font-medium mb-1.5">
              Confirm Password
            </label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={8}
              className="w-full px-4 py-3 rounded-lg border border-mist bg-cream text-sm text-ink placeholder:text-ghost focus:outline-none focus:border-amber transition-colors"
              placeholder="Repeat your password"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-ink text-cream rounded-lg text-sm font-semibold hover:bg-amber disabled:opacity-50 transition-colors cursor-pointer disabled:cursor-not-allowed"
          >
            {loading ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        <p className="text-center text-xs text-ghost mt-6">
          Already have an account?{' '}
          <Link to="/login" className="text-amber hover:text-rust font-medium transition-colors">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
