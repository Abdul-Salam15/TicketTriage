"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

export default function Navbar() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    setLoggedIn(!!window.localStorage.getItem("tt_token"));
  }, []);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      /* ignore logout errors */
    }
    window.localStorage.removeItem("tt_token");
    window.location.href = "/";
  }

  return (
    <header className="navbar">
      <a href="/" className="brand">TicketTriage</a>
      <nav className="nav-links">
        {loggedIn ? (
          <>
            <a href="/" className="nav-link">Submit</a>
            <a href="/tickets" className="nav-link">All Tickets</a>
            <button className="nav-link nav-button" onClick={handleLogout} disabled={loggingOut}>
              Logout
            </button>
          </>
        ) : (
          <>
            <a href="/login" className="nav-link">Login</a>
            <a href="/register" className="nav-link">Register</a>
          </>
        )}
      </nav>
    </header>
  );
}
