import { useId, useRef, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { Button } from "../ui/Button";
import { BrandMark, Notice, Spinner } from "../ui/feedback";
import { useAuth } from "./AuthContext";

const field =
  "mt-1.5 block h-10 w-full rounded-control border bg-surface px-3 text-control text-ink " +
  "placeholder:text-faint focus:border-accent focus:outline-none";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Incorrect username or password.";
    if (error.status === 429) {
      return error.retryAfter
        ? `Too many sign-in attempts. Try again in ${error.retryAfter} seconds.`
        : "Too many sign-in attempts. Try again in a minute.";
    }
    return error.message;
  }
  return "Sign-in failed. Try again.";
}

export function LoginView() {
  const { session, signIn, signOutReason } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const passwordInput = useRef<HTMLInputElement>(null);
  const ids = { username: useId(), password: useId(), error: useId() };

  if (session) return <Navigate to={from} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await signIn(username.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
      setPassword("");
      setSubmitting(false);
      passwordInput.current?.focus();
    }
  }

  return (
    <div className="flex min-h-full items-start justify-center bg-canvas px-4 py-[12vh]">
      <main className="w-full max-w-[400px]">
        <div className="mb-8 flex items-center gap-2.5">
          <BrandMark size={28} />
          <span className="text-lead font-semibold tracking-[-0.01em] text-ink">Policy Copilot</span>
        </div>

        <div className="rounded-panel border border-line bg-surface p-6 shadow-composer sm:p-7">
          <h1 className="text-heading font-semibold tracking-[-0.015em] text-ink">Sign in</h1>
          <p className="mt-1.5 text-control text-muted">Use your Policy Copilot account.</p>

          {signOutReason === "expired" && !error && (
            <div className="mt-5">
              <Notice tone="warning">Your session expired. Sign in again to continue.</Notice>
            </div>
          )}

          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            <div>
              <label htmlFor={ids.username} className="block text-ui font-medium text-ink">
                Username
              </label>
              <input
                id={ids.username}
                name="username"
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                autoFocus
                required
                aria-invalid={Boolean(error) || undefined}
                aria-describedby={error ? ids.error : undefined}
                className={`${field} ${error ? "border-danger" : "border-line-strong"}`}
              />
            </div>

            <div>
              <label htmlFor={ids.password} className="block text-ui font-medium text-ink">
                Password
              </label>
              <div className="relative">
                <input
                  id={ids.password}
                  ref={passwordInput}
                  name="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                  aria-invalid={Boolean(error) || undefined}
                  aria-describedby={error ? ids.error : undefined}
                  className={`${field} pr-16 ${error ? "border-danger" : "border-line-strong"}`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((shown) => !shown)}
                  aria-pressed={showPassword}
                  aria-controls={ids.password}
                  className="absolute top-1/2 right-1.5 h-7 -translate-y-1/2 rounded-control px-2 text-ui font-medium text-muted hover:bg-sunken hover:text-ink"
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </div>

            {error && (
              <p id={ids.error} role="alert" className="text-ui text-danger">
                {error}
              </p>
            )}

            <Button
              type="submit"
              variant="primary"
              className="w-full"
              disabled={!username.trim() || !password || submitting}
            >
              {submitting ? (
                <>
                  <Spinner size={14} /> Signing in…
                </>
              ) : (
                "Sign in"
              )}
            </Button>
          </form>
        </div>

        <p className="mt-5 px-1 text-ui text-muted">
          Don't have an account? Ask your Policy Copilot administrator.
        </p>

        {import.meta.env.DEV && (
          <div className="mt-6 px-1 text-ui text-muted">
            <p>For local development, create an account from the project root:</p>
            <pre className="mt-2 whitespace-pre-wrap rounded-control border border-line bg-surface px-3 py-2 font-mono text-meta text-ink-soft">
              python -m app.cli.users create alice --roles employee
            </pre>
          </div>
        )}
      </main>
    </div>
  );
}
