import { useState, type FormEvent } from "react";
import { fetchMe, login, type MeResponse } from "../api/auth";
import { ApiError } from "../api/client";

export function LoginPage({ onSuccess, onRegister }: { onSuccess: (session: MeResponse) => void; onRegister: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      onSuccess(await fetchMe());
    } catch (err) {
      console.error("Login failed error:", err);
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "Invalid email or password." : err.message);
      } else if (err instanceof Error) {
        setError(`Connection failed: ${err.message}. Check CORS_ORIGINS on Railway.`);
      } else {
        setError("Login failed. Please check network/CORS settings.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <h1>Commerce Analytics MCP</h1>
      <p className="lede">Sign in with your organization account to view commerce analytics.</p>
      <section className="panel">
        <h2>Sign in</h2>
        <form className="form" onSubmit={onSubmit}>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        {error ? <p className="error">{error}</p> : null}
        <p className="muted">
          No account yet?{" "}
          <button type="button" className="link" onClick={onRegister}>
            Create one
          </button>
        </p>
      </section>
    </main>
  );
}
