import hashlib
import random
import secrets
import string
import time
import threading

from collections import defaultdict
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Base, engine, SessionLocal, get_db
from models import Ticket, User, SessionToken
from schemas import (
    TicketCreate,
    TicketResponse,
    TicketReplyUpdate,
    TicketAnalytics,
    UserAuth,
    UserResponse,
    UserLogin,
    AuthResponse,
)
from llm.factory import get_llm_provider

REGENERATE_LIMIT = 3
REGENERATE_WINDOW_SECONDS = 300.0
regenerate_attempts: dict[int, list[float]] = defaultdict(list)
regenerate_lock = threading.Lock()

CODE_ALPHABET = string.ascii_uppercase + string.digits


def _generate_ticket_code() -> str:
    return "".join(random.choices(CODE_ALPHABET, k=7))


def _generate_unique_ticket_code(db: Session) -> str:
    while True:
        code = _generate_ticket_code()
        if not db.query(Ticket).filter(Ticket.ticket_code == code).first():
            return code


def _migrate_db_schema() -> None:
    # quick and dirty schema migration — just adds columns if they're missing.
    # good enough for a prototype, would use alembic in production
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if "tickets" in table_names:
        columns = [column["name"] for column in inspector.get_columns("tickets")]

        if "ticket_code" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE tickets ADD COLUMN ticket_code VARCHAR(7)"))
                conn.commit()

        if "user_id" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE tickets ADD COLUMN user_id INTEGER"))
                conn.commit()

        # backfill any existing tickets that don't have a code yet
        with SessionLocal() as db:
            missing = db.query(Ticket).filter((Ticket.ticket_code == None) | (Ticket.ticket_code == "")).all()
            for ticket in missing:
                ticket.ticket_code = _generate_unique_ticket_code(db)
            if missing:
                db.commit()

    # if the users table still has the old schema (username column instead of email),
    # just nuke it and start fresh — there won't be any real users in dev anyway
    if "users" in table_names:
        user_columns = [column["name"] for column in inspector.get_columns("users")]
        if "email" not in user_columns:
            with engine.connect() as conn:
                conn.execute(text("DROP TABLE IF EXISTS session_tokens"))
                conn.execute(text("DROP TABLE users"))
                conn.commit()
            Base.metadata.create_all(bind=engine)


def _friendly_llm_error(error: Exception) -> str:
    # translate raw LLM errors into something the user can actually understand
    message = str(error).lower()

    if "invalid_api_key" in message or "incorrect api key" in message or "missing credentials" in message:
        return "AI classification failed because the backend OpenAI credentials are invalid. Please check your API key and try again."
    if "rate limit" in message or "too many requests" in message:
        return "AI classification is temporarily rate-limited. Please wait a moment and try again."
    if "timeout" in message:
        return "AI classification timed out. Please try again in a few seconds."
    if "quota" in message or "insufficient_quota" in message:
        return "AI classification failed due to quota limits. Please check your OpenAI account usage."

    return "AI classification failed. Please try again later."


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _verify_password(password: str, password_hash: str) -> bool:
    return _hash_password(password) == password_hash


def _make_token() -> str:
    return secrets.token_urlsafe(32)


def _create_session_token(db: Session, user: User) -> str:
    token = _make_token()
    session = SessionToken(token=token, user_id=user.id)
    db.add(session)
    db.commit()
    return token


def _get_user_from_token(db: Session, token: str) -> Optional[User]:
    session = db.query(SessionToken).filter(SessionToken.token == token).first()
    if not session:
        return None
    return db.query(User).filter(User.id == session.user_id).first()


def get_current_user(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization token")

    token = authorization.split(" ", 1)[1]
    user = _get_user_from_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


# create tables if they don't exist yet
Base.metadata.create_all(bind=engine)
_migrate_db_schema()

app = FastAPI(title="TicketTriage API")

# need this otherwise the browser blocks requests from localhost:3000 -> localhost:8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/tickets", response_model=TicketResponse, status_code=201)
async def create_ticket(ticket: TicketCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # validate -> call LLM -> save to db -> return
    provider = get_llm_provider()

    try:
        result = await provider.triage_ticket(ticket.subject, ticket.description)
    except Exception as e:
        # don't save a half-done ticket if the LLM call fails
        raise HTTPException(
            status_code=502,
            detail=_friendly_llm_error(e),
        )

    db_ticket = Ticket(
        ticket_code=_generate_unique_ticket_code(db),
        user_id=user.id,
        subject=ticket.subject,
        description=ticket.description,
        category=result.category,
        priority=result.priority,
        suggested_reply=result.reply,
    )
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)

    return db_ticket


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(user_auth: UserAuth, db: Session = Depends(get_db)):
    user = User(email=user_auth.email, password_hash=_hash_password(user_auth.password))
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="A user with that email already exists")

    token = _create_session_token(db, user)
    return AuthResponse(user=UserResponse.from_orm(user), token=token)


@app.post("/auth/login", response_model=AuthResponse)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    email = login_data.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not _verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _create_session_token(db, user)
    return AuthResponse(user=UserResponse.from_orm(user), token=token)


@app.post("/auth/logout")
def logout(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization token")
    token = authorization.split(" ", 1)[1]
    db.query(SessionToken).filter(SessionToken.token == token).delete()
    db.commit()
    return {"detail": "Logged out"}


@app.get("/auth/me", response_model=UserResponse)
def get_current_user_info(user: User = Depends(get_current_user)):
    return user


@app.get("/tickets", response_model=list[TicketResponse])
def list_tickets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Ticket).filter(Ticket.user_id == user.id).order_by(Ticket.created_at.desc()).all()


@app.get("/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user.id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


def _check_regenerate_rate_limit(ticket_id: int) -> None:
    now = time.time()
    with regenerate_lock:
        attempts = regenerate_attempts[ticket_id]
        # drop attempts outside the window
        regenerate_attempts[ticket_id] = [ts for ts in attempts if now - ts < REGENERATE_WINDOW_SECONDS]
        if len(regenerate_attempts[ticket_id]) >= REGENERATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"You can only regenerate a reply {REGENERATE_LIMIT} times every 5 minutes for this ticket.",
            )
        regenerate_attempts[ticket_id].append(now)


@app.patch("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket_reply(ticket_id: int, payload: TicketReplyUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user.id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if payload.regenerate:
        _check_regenerate_rate_limit(ticket_id)
        provider = get_llm_provider()
        try:
            result = await provider.triage_ticket(ticket.subject, ticket.description)
        except Exception as e:
            raise HTTPException(status_code=502, detail=_friendly_llm_error(e))
        ticket.suggested_reply = result.reply
    elif payload.reply:
        ticket.suggested_reply = payload.reply

    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@app.get("/analytics", response_model=TicketAnalytics)
def ticket_analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tickets = db.query(Ticket).filter(Ticket.user_id == user.id).all()

    category_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}

    for t in tickets:
        category_counts[t.category or "Uncategorized"] = category_counts.get(t.category or "Uncategorized", 0) + 1
        priority_counts[t.priority or "Unknown"] = priority_counts.get(t.priority or "Unknown", 0) + 1

    return TicketAnalytics(category_counts=category_counts, priority_counts=priority_counts)
