import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Navigate, useLocation } from "react-router-dom";
import { login } from "../api/auth";
import { configureAuth } from "../api/client";
import { clearPassageCache } from "../api/sources";
import { abortAllTurns } from "../chat/turns";
import { clearSession, loadSession, parseToken, saveSession, type Session } from "./session";

export type SignOutReason = "expired" | "signed_out";

interface AuthValue {
  session: Session | null;
  /** Why the last session ended, shown once on the sign-in screen. */
  signOutReason: SignOutReason | null;
  /** Throws ApiError (401 wrong credentials, 429 too many attempts). */
  signIn: (username: string, password: string) => Promise<void>;
  signOut: (reason?: SignOutReason) => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

/** The signed-in session; only valid inside <RequireAuth>. */
export function useSession(): Session {
  const { session } = useAuth();
  if (!session) throw new Error("useSession used outside an authenticated route");
  return session;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [initial] = useState(loadSession);
  const [session, setSession] = useState<Session | null>(initial.session);
  const [signOutReason, setSignOutReason] = useState<SignOutReason | null>(
    initial.expired ? "expired" : null,
  );

  const signOut = useCallback((reason: SignOutReason = "signed_out") => {
    abortAllTurns();
    clearPassageCache();
    clearSession();
    setSession(null);
    setSignOutReason(reason);
  }, []);

  // Layout effect: runs before any child's data-fetching effect, so the
  // first request already carries the token and the 401 handler.
  useLayoutEffect(() => {
    configureAuth(session?.token ?? null, session ? () => signOut("expired") : null);
  }, [session, signOut]);

  // End the session when the token's lifetime is up, even if the tab is idle.
  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => signOut("expired"), session.expiresAt - Date.now());
    return () => window.clearTimeout(timer);
  }, [session, signOut]);

  const signIn = useCallback(async (username: string, password: string) => {
    const { access_token } = await login(username, password);
    // Claims are read for display only; the API verifies every request.
    const next = parseToken(access_token);
    saveSession(next);
    setSession(next);
    setSignOutReason(null);
  }, []);

  const value = useMemo(
    () => ({ session, signOutReason, signIn, signOut }),
    [session, signOutReason, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Route guard: unauthenticated visitors go to sign-in and come back afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const location = useLocation();

  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}
