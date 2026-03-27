import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { login as apiLogin, register as apiRegister, clearTokens, isAuthenticated } from '../utils/api';
import type { User } from '../types/api';

interface AuthContextType {
  user: User | null;
  isLoggedIn: boolean;
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

function userFromToken(): User | null {
  const token = localStorage.getItem('access_token');
  if (!token) return null;
  const payload = parseJwt(token);
  if (!payload) return null;
  return {
    id: payload.sub as string,
    username: payload.username as string,
    email: '',
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(userFromToken);

  useEffect(() => {
    if (isAuthenticated() && !user) {
      setUser(userFromToken());
    }
  }, [user]);

  const login = useCallback(async (username: string, password: string) => {
    await apiLogin(username, password);
    setUser(userFromToken());
  }, []);

  const register = useCallback(async (username: string, password: string, email: string) => {
    await apiRegister(username, password, email);
    setUser(userFromToken());
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoggedIn: !!user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
