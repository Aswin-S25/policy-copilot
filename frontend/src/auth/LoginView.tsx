import { useId, useMemo, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button } from "../ui/Button";
import { BrandMark, Notice, Spinner } from "../ui/feedback";
import { useAuth } from "./AuthContext";
import { formatExpiry, parseToken, roleName, TokenError } from "./session";

export function LoginView() {
  const { session, signIn, signOutReason } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const fieldId = useId();

  // Show whose token this is before it's submitted. Display only: the API
  // verifies the signature when the form is sent.
  const preview = useMemo(() => {
    if (!token.trim()) return null;
    try {
      return parseToken(token);
    } catch {
      return null;
    }
  }, [token]);

  if (session) return <Navigate to={from} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await signIn(token);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof TokenError || err instanceof Error ? err.message : "Sign-in failed. Try again.");
      setSubmitting(false);
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
          <p className="mt-1.5 text-control text-muted">
            Paste the access token issued for your account.
          </p>

          {signOutReason === "expired" && !error && (
            <div className="mt-5">
              <Notice tone="warning">Your session expired. Sign in again to continue.</Notice>
            </div>
          )}

          <form onSubmit={submit} className="mt-6" noValidate>
            <label htmlFor={fieldId} className="block text-ui font-medium text-ink">
              Access token
            </label>
            <input
              id={fieldId}
              type="password"
              value={token}
              onChange={(event) => {
                setToken(event.target.value);
                setError(null);
              }}
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              autoFocus
              placeholder="eyJhbGciOi…"
              aria-invalid={Boolean(error) || undefined}
              aria-describedby={`${fieldId}-hint`}
              className={
                "mt-1.5 block h-10 w-full rounded-control border bg-surface px-3 font-mono text-ui text-ink " +
                "placeholder:text-faint focus:border-accent focus:outline-none focus-visible:outline-2 " +
                "focus-visible:outline-offset-0 focus-visible:outline-accent/30 " +
                (error ? "border-danger" : "border-line-strong")
              }
            />

            <div id={`${fieldId}-hint`} className="mt-2 min-h-5 text-ui">
              {error ? (
                <p role="alert" className="text-danger">{error}</p>
              ) : preview ? (
                <p className="text-muted">
                  Signs in as <span className="font-medium text-ink">{preview.subject}</span>
                  {preview.roles.length > 0 && <> with {preview.roles.map(roleName).join(", ")} access</>}.
                  Expires {formatExpiry(preview.expiresAt)}.
                </p>
              ) : null}
            </div>

            <Button type="submit" variant="primary" className="mt-4 w-full" disabled={!token.trim() || submitting}>
              {submitting ? (
                <>
                  <Spinner size={14} /> Checking token…
                </>
              ) : (
                "Sign in"
              )}
            </Button>
          </form>
        </div>

        {import.meta.env.DEV && (
          <div className="mt-6 px-1 text-ui text-muted">
            <p>For local development, issue a token from the project root:</p>
            <pre className="mt-2 whitespace-pre-wrap rounded-control border border-line bg-surface px-3 py-2 font-mono text-meta text-ink-soft">
              python -m app.cli.issue_token --sub alice --roles employee
            </pre>
          </div>
        )}
      </main>
    </div>
  );
}
