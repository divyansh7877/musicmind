import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { useAuth as useClerkAuth, useUser } from '@clerk/react';
import { clearTokens } from '../utils/api';
import type { User } from '../types/api';

const DEMO_USER: User = { id: '00000000-0000-0000-0000-000000000000', username: 'demo', email: 'demo@musicmind.local' };

interface AuthContextType {
  user: User | null;
  isLoggedIn: boolean;
  demoMode: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, email: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

function parseJwt(token: string): Record<string, unknown> | null {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

function userFromClerk(user: ReturnType<typeof useUser>['user']): User | null {
  if (!user) return null;
  return {
    id: user.id,
    username: user.username || user.primaryEmailAddress?.emailAddress?.split('@')[0] || user.id,
    email: user.primaryEmailAddress?.emailAddress || '',
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { isSignedIn } = useClerkAuth();
  const { user } = useUser();
  const [userState, setUserState] = useState<User | null>(() =>
    isSignedIn ? userFromClerk(user) : null,
  );
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then((cfg) => {
        if (cfg.demo_mode) {
          setDemoMode(true);
          setUserState(DEMO_USER);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!demoMode) {
      setUserState(isSignedIn ? userFromClerk(user) : null);
    }
  }, [isSignedIn, user, demoMode]);

  const login = useCallback(async (_username: string, _password: string) => {
    // Login is handled by Clerk's <SignIn> component — no-op here
    // Kept for backwards compat with code calling useAuth().login()
  }, []);

  const register = useCallback(async (_username: string, _password: string, _email: string) => {
    // Registration is handled by Clerk's <SignUp> component — no-op here
  }, []);

  const logout = useCallback(() => {
    if (demoMode) return;
    // Clerk handles sign-out via window.Clerk.signOut() triggered by UserButton
    clearTokens();
  }, [demoMode]);

  return (
    <AuthContext.Provider
      value={{ user: userState, isLoggedIn: demoMode || isSignedIn, demoMode, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

