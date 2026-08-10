"use client";

import { useEffect, useState } from "react";

export default function Navbar() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    setLoggedIn(!!window.localStorage.getItem("tt_token"));
  }, []);

  async function handleLogout() {
    const token = window.localStorage.getItem("tt_token");
    if (token) {
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {});
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
