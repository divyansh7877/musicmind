import { createContext, useContext, useCallback, type ReactNode } from 'react';
import { useAuth as useClerkAuth, useUser } from '@clerk/react';
import { clearTokens } from '../utils/api';
import type { User } from '../types/api';

interface AuthContextType {
  user: User | null;
  isLoggedIn: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, email: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

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

  const userState = isSignedIn ? userFromClerk(user) : null;

  const login = useCallback(async () => {
  }, []);

  const register = useCallback(async () => {
  }, []);

  const logout = useCallback(() => {
    clearTokens();
  }, []);

  return (
    <AuthContext.Provider
      value={{ user: userState, isLoggedIn: !!isSignedIn, login, register, logout }}
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

