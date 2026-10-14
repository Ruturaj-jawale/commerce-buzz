import { useState, type FormEvent } from "react";
import { fetchMe, register, type MeResponse, type RegisterResponse } from "../api/auth";
import { ApiError } from "../api/client";

export function RegisterPage({ onSuccess, onSignIn }: { onSuccess: (session: MeResponse) => void; onSignIn: () => void }) {
  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmed, setConfirmed] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<RegisterResponse | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmed) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setCreated(await register(organizationName, email, password));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setError("That email already has an account. Sign in instead.");
      else if (err instanceof ApiError && err.status === 403) setError("Registration is disabled on this deployment.");
      else if (err instanceof ApiError && err.status === 422) setError("Check the organization name, email, and a password of at least 8 characters.");
      else setError("Could not create your account. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function enterDashboard() {
    setBusy(true);
    try {
      onSuccess(await fetchMe());
    } catch {
      setError("Session could not be restored. Sign in with your new account.");
      setCreated(null);
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <main className="page">
        <h1>Welcome to {created.organization.name}</h1>
        <p className="lede">
          Your account is ready and signed in. Save the API key now — it is shown only once and is what your
          servers, webhooks, and MCP client use to send data.
        </p>
        <section className="panel">
          <p className="label">Initial API key</p>
          <code className="secret">{created.api_key.key}</code>
          <p className="label">Organization slug: {created.organization.slug}</p>
          <div className="actions">
            <button type="button" onClick={() => void navigator.clipboard.writeText(created.api_key.key)}>
              Copy key
            </button>
            <button type="button" disabled={busy} onClick={() => void enterDashboard()}>
              {busy ? "Opening…" : "Go to dashboard"}
            </button>
          </div>
        </section>
        {error ? <p className="error">{error}</p> : null}
      </main>
    );
  }

  return (
    <main className="page">
      <h1>Create your account</h1>
      <p className="lede">
        Every account gets its own organization. Orders, payments, and analytics never cross between organizations.
      </p>
      <section className="panel">
        <h2>Sign up</h2>
        <form className="form" onSubmit={onSubmit}>
          <label>
            Organization name
            <input
              value={organizationName}
              onChange={(event) => setOrganizationName(event.target.value)}
              placeholder="Acme Commerce"
              autoComplete="organization"
              required
            />
          </label>
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
              autoComplete="new-password"
              minLength={8}
              required
            />
          </label>
          <label>
            Confirm password
            <input
              type="password"
              value={confirmed}
              onChange={(event) => setConfirmed(event.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "Creating account…" : "Create account"}
          </button>
        </form>
        {error ? <p className="error">{error}</p> : null}
        <p className="muted">
          Already have an account?{" "}
          <button type="button" className="link" onClick={onSignIn}>
            Sign in
          </button>
        </p>
      </section>
    </main>
  );
}
