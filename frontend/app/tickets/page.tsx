"use client";

import { useEffect, useState } from "react";

const priorityClass: Record<string, string> = {
  High: "badge-high",
  Med: "badge-med",
  Low: "badge-low",
};

async function getTickets(token: string) {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/tickets`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load tickets");
  return res.json();
}

async function getAnalytics(token: string) {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/analytics`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load analytics");
  return res.json();
}

interface AnalyticsData {
  category_counts: Record<string, number>;
  priority_counts: Record<string, number>;
}

export default function TicketsPage() {
  const [tickets, setTickets] = useState<any[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = typeof window !== "undefined" ? window.localStorage.getItem("tt_token") : null;
    if (!token) {
      setError("Please login to view your tickets.");
      setLoading(false);
      return;
    }

    Promise.all([getTickets(token), getAnalytics(token)])
      .then(([ticketsData, analyticsData]) => {
        setTickets(ticketsData);
        setAnalytics(analyticsData);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load your tickets"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <section className="section">Loading your tickets...</section>;
  }

  if (error) {
    return <section className="section"><div className="alert-error">{error}</div></section>;
  }

  return (
    <section className="section">
      <div className="section-header">
        <div>
          <p className="eyebrow">Your ticket history</p>
          <h1 className="page-title">All Tickets</h1>
        </div>
      </div>

      <div className="analytics-grid">
        <div className="analytics-card">
          <h2>Tickets by Category</h2>
          <ul>
            {Object.entries(analytics.category_counts).map(([category, count]) => (
              <li key={category} className="analytics-row">
                <strong>{category}</strong>
                <span>{count}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="analytics-card">
          <h2>Tickets by Priority</h2>
          <ul>
            {Object.entries(analytics.priority_counts).map(([priority, count]) => (
              <li key={priority} className="analytics-row">
                <strong>{priority}</strong>
                <span>{count}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="ticket-list">
        {tickets.map((ticket: any) => (
          <a key={ticket.id} href={`/tickets/${ticket.id}`} className="ticket-card">
            <div className="ticket-header">
              <div>
                <p className="ticket-title">{ticket.subject}</p>
                <p className="ticket-meta">{ticket.ticket_code} · {ticket.category} · {ticket.status} · {new Date(ticket.created_at).toLocaleString()}</p>
              </div>
              <span className={`badge ${priorityClass[ticket.priority] || "badge-low"}`}>
                {ticket.priority}
              </span>
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}
