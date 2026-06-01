"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";

import { apiFetch, getStoredToken, setStoredToken } from "./api";

export type Usuario = {
  id: number;
  nome: string;
  email: string;
  is_admin: boolean;
};

type TokenResponse = { access_token: string; token_type: string };

type AuthContextValue = {
  user: Usuario | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (nome: string, email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Usuario | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Carrega token do localStorage no mount e tenta hidratar `user` via /auth/me.
  useEffect(() => {
    const stored = getStoredToken();
    if (!stored) {
      setLoading(false);
      return;
    }
    setToken(stored);
    apiFetch<Usuario>("/api/v1/auth/me")
      .then((u) => setUser(u))
      .catch(() => {
        // Token invalido ou expirado: limpa.
        setStoredToken(null);
        setToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const persistToken = useCallback(async (newToken: string) => {
    setStoredToken(newToken);
    setToken(newToken);
    const u = await apiFetch<Usuario>("/api/v1/auth/me");
    setUser(u);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await apiFetch<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        skipAuth: true,
        body: JSON.stringify({ email, password }),
      });
      await persistToken(res.access_token);
    },
    [persistToken],
  );

  const register = useCallback(
    async (nome: string, email: string, password: string) => {
      const res = await apiFetch<TokenResponse>("/api/v1/auth/register", {
        method: "POST",
        skipAuth: true,
        body: JSON.stringify({ nome, email, password }),
      });
      await persistToken(res.access_token);
    },
    [persistToken],
  );

  const logout = useCallback(() => {
    setStoredToken(null);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth deve ser usado dentro de <AuthProvider>");
  }
  return ctx;
}
