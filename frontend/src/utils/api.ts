import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type {
  SearchResponse,
  GraphTraversalResponse,
  TokenResponse,
  ActivityResponse,
  FeedbackRequest,
  NLQueryResponse,
  ExplosionResponse,
} from '../types/api';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

function getToken(): string | null {
  // Try Clerk session token first
  try {
    if (typeof window !== 'undefined' && (window as any).Clerk?.session) {
      // Clerk session token is read synchronously from cookie/local state
      const session = (window as any).Clerk.session;
      if (session && typeof session.getToken === 'function') {
        return session.getToken() as string | null;
      }
    }
  } catch {
    // Fall through to custom JWT
  }
  // Fall back to custom JWT (backwards compat when Clerk not configured)
  return localStorage.getItem('access_token');
}

function getRefreshToken(): string | null {
  return localStorage.getItem('refresh_token');
}

function setTokens(access: string, refresh: string) {
  localStorage.setItem('access_token', access);
  localStorage.setItem('refresh_token', refresh);
}

export function clearTokens() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const token = await getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;

      // Check if Clerk is configured — Clerk handles token refresh internally;
      // if Clerk token is invalid, redirect to sign-in directly.
      try {
        const clerkSession = (window as any).Clerk?.session;
        if (clerkSession) {
          window.location.href = '/login';
          return Promise.reject(error);
        }
      } catch {
        // Clerk not available, fall through to JWT refresh
      }

      // Try custom JWT refresh (backwards compat)
      const refresh = getRefreshToken();
      if (refresh) {
        try {
          const { data } = await axios.post<TokenResponse>(
            '/api/auth/refresh',
            null,
            { params: { refresh_token: refresh } },
          );
          setTokens(data.access_token, data.refresh_token);
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return api(original);
        } catch {
          clearTokens();
          window.location.href = '/login';
        }
      } else {
        clearTokens();
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

export async function searchSong(songName: string): Promise<SearchResponse> {
  const { data } = await api.post<SearchResponse>('/search', { song_name: songName });
  return data;
}

export async function traverseGraph(
  nodeId: string,
  maxDepth = 2,
  searchResult?: Record<string, unknown>,
): Promise<GraphTraversalResponse> {
  const { data } = await api.post<GraphTraversalResponse>(`/graph/${nodeId}`, {
    max_depth: maxDepth,
    search_result: searchResult ?? null,
  });
  return data;
}

export async function getFullGraph(): Promise<GraphTraversalResponse> {
  const { data } = await api.get<GraphTraversalResponse>('/graph/full');
  return data;
}

export async function submitFeedback(feedback: FeedbackRequest): Promise<void> {
  await api.post('/feedback', feedback);
}

export async function getActivity(limit = 50, offset = 0): Promise<ActivityResponse> {
  const { data } = await api.get<ActivityResponse>('/activity', { params: { limit, offset } });
  return data;
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>(
    '/auth/login',
    null,
    { params: { username, password } },
  );
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function register(
  username: string,
  password: string,
  email: string,
): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>(
    '/auth/register',
    null,
    { params: { username, password, email } },
  );
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function queryGraph(question: string): Promise<NLQueryResponse> {
  const { data } = await api.post<NLQueryResponse>('/query', { question });
  return data;
}

export async function explodeGraph(): Promise<ExplosionResponse> {
  const { data } = await api.post<ExplosionResponse>('/graph/explode');
  return data;
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

export default api;
