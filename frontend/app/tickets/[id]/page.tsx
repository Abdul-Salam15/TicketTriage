'use client';

import { useEffect, useState } from "react";
import { apiFetch } from "../../lib/api";
import type { Ticket } from "../../lib/types";

export default function TicketDetail({ params }: { params: { id: string } }) {
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [successMessage, setSuccessMessage] = useState("");
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const data = await apiFetch<Ticket>(`/tickets/${params.id}`);
        setTicket(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load ticket");
      } finally {
        setLoading(false);
      }
    }

    load();

    if (typeof window !== "undefined") {
      const submittedTicket = window.sessionStorage.getItem("ticketSubmitted");
      if (submittedTicket === params.id) {
        setSubmitted(true);
        window.sessionStorage.removeItem("ticketSubmitted");
      }
    }
  }, [params.id]);

  if (!ticket) {
    return (
      <section className="section">
        {error && <div className="alert-error">{error}</div>}
        {!error && <div>Loading ticket...</div>}
      </section>
    );
  }

  async function regenerateReply() {
    setSaving(true);
    setError("");
    setSuccessMessage("");

    try {
      const updated = await apiFetch<Ticket>(`/tickets/${params.id}`, {
        method: "PATCH",
        body: JSON.stringify({ regenerate: true }),
      });
      setTicket(updated);
      setEditing(false);
      setSuccessMessage("Reply regenerated successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to regenerate reply");
    } finally {
      setSaving(false);
    }
  }

  async function saveEdit() {
    if (!editText.trim()) return;
    setSaving(true);
    setError("");
    setSuccessMessage("");

    try {
      const updated = await apiFetch<Ticket>(`/tickets/${params.id}`, {
        method: "PATCH",
        body: JSON.stringify({ reply: editText.trim() }),
      });
      setTicket(updated);
      setEditing(false);
      setSuccessMessage("Reply updated successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save reply");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="section">
      {submitted && ticket?.ticket_code && (
        <div className="alert-success">Ticket submitted successfully! Ticket ID: {ticket.ticket_code}</div>
      )}
      {successMessage && <div className="alert-success">{successMessage}</div>}
      {error && <div className="alert-error">{error}</div>}

      <div className="section-header">
        <div>
          <p className="eyebrow">Ticket details</p>
          <h1 className="page-title">{ticket.subject}</h1>
          <div className="ticket-info-row">
            <div className="ticket-info-item">
              <span className="ticket-info-label">Ticket ID</span>
              <span className="ticket-info-value">{ticket.ticket_code}</span>
            </div>
            <div className="ticket-info-item">
              <span className="ticket-info-label">Category</span>
              <span className="ticket-info-value">{ticket.category}</span>
            </div>
            <div className="ticket-info-item">
              <span className="ticket-info-label">Priority</span>
              <span className={`ticket-badge ${ticket.priority === "High" ? "badge-high" : ticket.priority === "Med" ? "badge-med" : "badge-low"}`}>
                {ticket.priority}
              </span>
            </div>
            <div className="ticket-info-item">
              <span className="ticket-info-label">Status</span>
              <span className="ticket-info-value">{ticket.status}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="detail-card">
        <p className="label">Original Description</p>
        <p className="detail-text">{ticket.description}</p>
      </div>

      <div className="detail-card" style={{ marginTop: "1rem" }}>
        <div className="reply-header">
          <p className="label">Suggested Reply</p>
          <div className="reply-actions">
            {editing ? (
              <>
                <button type="button" onClick={saveEdit} disabled={saving || !editText.trim()} className="button button-primary">
                  {saving ? "Saving..." : "Save"}
                </button>
                <button type="button" onClick={() => setEditing(false)} disabled={saving} className="button button-secondary">
                  Cancel
                </button>
              </>
            ) : (
              <>
                <button type="button" onClick={() => { setEditText(ticket.suggested_reply || ""); setEditing(true); }} className="button button-secondary">
                  Edit Reply
                </button>
                <button type="button" onClick={regenerateReply} disabled={saving} className="button button-primary">
                  {saving ? "Regenerating..." : "Regenerate Reply"}
                </button>
              </>
            )}
          </div>
        </div>
        {editing ? (
          <textarea
            className="textarea"
            rows={6}
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
          />
        ) : (
          <p className="detail-text">{ticket.suggested_reply}</p>
        )}
      </div>
    </section>
  );
}
