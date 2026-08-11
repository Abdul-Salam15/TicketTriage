"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "./lib/api";
import type { Ticket } from "./lib/types";

export default function Home() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  useEffect(() => {
    setLoggedIn(!!window.localStorage.getItem("tt_token"));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!subject.trim() || !description.trim()) {
      setError("Please fill in both fields.");
      return;
    }

    const token = window.localStorage.getItem("tt_token");
    if (!token) {
      setError("Please login or register before submitting a ticket.");
      return;
    }

    setLoading(true);
    try {
      const ticket = await apiFetch<Ticket>("/tickets", {
        method: "POST",
        body: JSON.stringify({ subject, description }),
      });

      if (typeof window !== "undefined") {
        window.sessionStorage.setItem("ticketSubmitted", String(ticket.id));
      }
      router.push(`/tickets/${ticket.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  if (!loggedIn) {
    return (
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Fast ticket triage with AI</p>
          <h1 className="page-title">Resolve support tickets faster</h1>
          <p className="page-text">
            TicketTriage uses AI to classify, prioritize, and draft replies for
            your support requests — so your team can focus on what matters.
          </p>
        </div>
        <div className="landing-actions">
          <a href="/register" className="button button-primary">Get Started</a>
          <a href="/login" className="button button-secondary">I have an account</a>
        </div>
      </section>
    );
  }

  return (
    <section className="hero">
      <div className="hero-copy">
        <p className="eyebrow">Fast ticket triage with AI</p>
        <h1 className="page-title">Submit your support request</h1>
        <p className="page-text">
          Describe the issue and let the backend classify the ticket, set priority, and provide a suggested reply.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="form-card">
        <div className="form-field">
          <label className="label">Subject</label>
          <input
            className="input"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Enter ticket subject"
          />
        </div>

        <div className="form-field">
          <label className="label">Description</label>
          <textarea
            className="textarea"
            rows={6}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the issue in detail"
          />
        </div>

        {error && <p className="error-message">{error}</p>}

        <button type="submit" disabled={loading} className="button button-primary">
          {loading ? "Working..." : "Submit Ticket"}
        </button>
      </form>
    </section>
  );
}
