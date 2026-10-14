import { useCallback, useEffect, useState } from "react";
import { fetchMe, logout, type MeResponse } from "./api/auth";
import { Dashboard } from "./pages/Dashboard";
import { LoginPage } from "./pages/Login";
import { RegisterPage } from "./pages/RegisterPage";

export default function App() {
  const [session, setSession] = useState<MeResponse | null>(null);
  const [checking, setChecking] = useState(true);
  const [authView, setAuthView] = useState<"login" | "register">("login");

  useEffect(() => {
    fetchMe()
      .then(setSession)
      .catch(() => setSession(null))
      .finally(() => setChecking(false));
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await logout();
    } catch {
      // The session may already be invalid; the cookie is cleared either way.
    }
    setSession(null);
  }, []);

  if (checking) {
    return (
      <main className="page">
        <p>Loading…</p>
      </main>
    );
  }

  if (!session) {
    return authView === "register" ? (
      <RegisterPage onSuccess={setSession} onSignIn={() => setAuthView("login")} />
    ) : (
      <LoginPage onSuccess={setSession} onRegister={() => setAuthView("register")} />
    );
  }

  return <Dashboard session={session} onLogout={() => void handleLogout()} />;
}
