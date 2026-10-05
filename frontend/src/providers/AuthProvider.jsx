import { createContext, useContext, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router";
import { api } from "../lib/api";
import { FullScreenLoader } from "../components/ui/Skeleton";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api("/auth/me"), retry: false, staleTime: 5 * 60_000 });

  useEffect(() => {
    const onUnauthorized = () => qc.setQueryData(["me"], null);
    window.addEventListener("ek:unauthorized", onUnauthorized);
    return () => window.removeEventListener("ek:unauthorized", onUnauthorized);
  }, [qc]);

  const value = {
    user: me.data ?? null,
    loading: me.isLoading,
    async login(email, password) {
      const u = await api("/auth/login", { method: "POST", body: { email, password } });
      qc.setQueryData(["me"], u);
      return u;
    },
    async register(name, email, password) {
      const u = await api("/auth/register", { method: "POST", body: { name, email, password } });
      qc.setQueryData(["me"], u);
      return u;
    },
    async logout() {
      await api("/auth/logout", { method: "POST" });
      qc.clear();
      qc.setQueryData(["me"], null);
    },
    can: (...roles) => !!me.data && roles.includes(me.data.role),
  };
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);

export function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullScreenLoader />;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return children;
}
