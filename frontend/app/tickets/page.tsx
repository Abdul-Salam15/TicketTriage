"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import type { Ticket, AnalyticsData } from "../lib/types";

const priorityClass: Record<string, string> = {
  High: "badge-high",
  Med: "badge-med",
  Low: "badge-low",
};

const barClass: Record<string, string> = {
  High: "bar-high",
  Med: "bar-med",
  Low: "bar-low",
};

function BarChart({ counts, colorByKey = false }: { counts: Record<string, number>; colorByKey?: boolean }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {
    return <p className="chart-empty">No tickets yet.</p>;
  }

  const max = Math.max(...entries.map(([, count]) => count));
  const yMax = Math.max(max, 1);
  const gridCount = Math.min(yMax, 5);

  return (
    <div className="chart-container">
      <div className="chart-graph">
        <div className="chart-gridlines">
          {Array.from({ length: gridCount }, (_, i) => (
            <div key={i} className="chart-gridline" />
          ))}
        </div>
        {entries.map(([label, count]) => (
          <div key={label} className="chart-bar-wrapper">
            <span className="chart-bar-count">{count}</span>
            <div className="chart-bar-track">
              <div
                className={`chart-bar ${colorByKey ? barClass[label] ?? "" : ""}`}
                style={{ height: `${Math.round((count / yMax) * 100)}%` }}
                role="img"
                aria-label={`${label}: ${count} ticket${count === 1 ? "" : "s"}`}
              />
            </div>
            <span className="chart-bar-label">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      apiFetch<Ticket[]>("/tickets"),
      apiFetch<AnalyticsData>("/analytics"),
    ])
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

  if (!analytics) {
    return <section className="section"><div className="alert-error">Unable to load analytics.</div></section>;
  }

  return (
    <section className="section">
      <div className="section-header">
        <div>
          <p className="eyebrow">Your ticket history</p>
          <h1 className="page-title">All Tickets ({tickets.length})</h1>
        </div>
      </div>

      <div className="analytics-grid">
        <div className="analytics-card">
          <h2>Tickets by Category</h2>
          <BarChart counts={analytics.category_counts} />
        </div>

        <div className="analytics-card">
          <h2>Tickets by Priority</h2>
          <BarChart counts={analytics.priority_counts} colorByKey />
        </div>
      </div>

      <div className="ticket-list">
        {tickets.map((ticket) => (
          <a key={ticket.id} href={`/tickets/${ticket.id}`} className="ticket-card">
            <div className="ticket-header">
              <div>
                <p className="ticket-title">{ticket.subject}</p>
                <p className="ticket-meta">{ticket.ticket_code} · {ticket.category} · {ticket.status} · {new Date(ticket.created_at).toLocaleString()}</p>
              </div>
              <span className={`badge ${priorityClass[ticket.priority ?? ""] || "badge-low"}`}>
                {ticket.priority}
              </span>
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}
