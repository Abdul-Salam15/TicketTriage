"use client";

import { useState } from "react";
import { apiFetch } from "../lib/api";

interface PasswordRule {
  label: string;
  test: (pw: string) => boolean;
}

const rules: PasswordRule[] = [
  { label: "At least 8 characters", test: (pw) => pw.length >= 8 },
  { label: "One uppercase letter", test: (pw) => /[A-Z]/.test(pw) },
  { label: "One lowercase letter", test: (pw) => /[a-z]/.test(pw) },
  { label: "One number", test: (pw) => /[0-9]/.test(pw) },
  { label: "One special character (!@#$%^&*...)", test: (pw) => /[!@#$%^&*()\\-_=+\[\]{}|;:',.<>?\/`~]/.test(pw) },
];

interface RegisterResponse {
  token: string;
}

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError("");

    if (!email.trim() || !password.trim()) {
      setError("Please enter both email and password.");
      return;
    }

    const failing = rules.filter((r) => !r.test(password));
    if (failing.length > 0) {
      setError(failing[0].label + ".");
      return;
    }

    setLoading(true);
    try {
      const data = await apiFetch<RegisterResponse>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      window.localStorage.setItem("tt_token", data.token);
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to register");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="section">
      <div className="section-header">
        <p className="eyebrow">Create an account</p>
        <h1 className="page-title">Register for TicketTriage</h1>
      </div>

      <form onSubmit={handleSubmit} className="form-card">
        <div className="form-field">
          <label className="label">Email</label>
          <input
            className="input"
            type="email"
            value={email}
            placeholder="you@example.com"
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="form-field">
          <label className="label">Password</label>
          <input
            className="input"
            type="password"
            value={password}
            placeholder="Choose a strong password"
            onChange={(e) => setPassword(e.target.value)}
          />
          {password.length > 0 && (
            <ul className="password-rules">
              {rules.map((rule) => (
                <li key={rule.label} className={rule.test(password) ? "rule-pass" : "rule-fail"}>
                  {rule.test(password) ? "\u2713" : "\u2717"} {rule.label}
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && <p className="error-message">{error}</p>}

        <button type="submit" className="button button-primary" disabled={loading}>
          {loading ? "Creating account..." : "Register"}
        </button>
      </form>
    </section>
  );
}
