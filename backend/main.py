import hashlib
import hmac
import logging
import os
import random
import secrets
import string
import time
import threading

from collections import defaultdict
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text, func as sa_func
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

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("tickettriage")

REGENERATE_LIMIT = 3
REGENERATE_WINDOW_SECONDS = 300.0
regenerate_attempts: dict[int, list[float]] = defaultdict(list)   # keyed by user_id
regenerate_lock = threading.Lock()

LOGIN_LIMIT = 5
LOGIN_WINDOW_SECONDS = 300.0
login_attempts: dict[str, list[float]] = defaultdict(list)
login_lock = threading.Lock()

CODE_ALPHABET = string.ascii_uppercase + string.digits


def _generate_ticket_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(7))


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

        # backfill orphaned tickets — assign to the first user so they aren't permanently invisible
        with SessionLocal() as db:
            orphans = db.query(Ticket).filter(Ticket.user_id == None).all()  # noqa: E711
            if orphans:
                first_user = db.query(User).order_by(User.id).first()
                if first_user:
                    for ticket in orphans:
                        ticket.user_id = first_user.id
                    db.commit()
                    logger.warning("Backfilled %d orphaned tickets to user_id=%d", len(orphans), first_user.id)
                else:
                    logger.warning("%d orphaned tickets exist but no users to assign them to", len(orphans))

        # backfill any existing tickets that don't have a code yet
        with SessionLocal() as db:
            missing = db.query(Ticket).filter((Ticket.ticket_code == None) | (Ticket.ticket_code == "")).all()
            for ticket in missing:
                ticket.ticket_code = _generate_unique_ticket_code(db)
            if missing:
                db.commit()

    # if the users table still has the old schema (username column instead of email),
    # the only migration path is a rebuild — gated behind an explicit opt-in so this
    # can never silently drop user data in a container restart loop
    if "users" in table_names:
        user_columns = [column["name"] for column in inspector.get_columns("users")]
        if "email" not in user_columns:
            if os.getenv("ALLOW_DESTRUCTIVE_MIGRATION") != "1":
                raise RuntimeError(
                    "users table has a pre-email schema. Re-run with "
                    "ALLOW_DESTRUCTIVE_MIGRATION=1 to drop and rebuild it (destroys all users), "
                    "or migrate the table manually."
                )
            logger.warning("Dropping legacy users/session_tokens tables — all user data will be lost")
            with engine.connect() as conn:
                conn.execute(text("DROP TABLE IF EXISTS session_tokens"))
                conn.execute(text("DROP TABLE users"))
                conn.commit()
            Base.metadata.create_all(bind=engine)


def _friendly_llm_error(error: Exception) -> str:
    # translate raw LLM errors into something the user can actually understand
    provider = os.getenv("LLM_PROVIDER", "openai").capitalize()
    message = str(error).lower()

    if "invalid_api_key" in message or "incorrect api key" in message or "missing credentials" in message:
        return f"AI classification failed because the backend {provider} credentials are invalid. Please check your API key and try again."
    if "rate limit" in message or "too many requests" in message:
        return "AI classification is temporarily rate-limited. Please wait a moment and try again."
    if "timeout" in message:
        return "AI classification timed out. Please try again in a few seconds."
    if "quota" in message or "insufficient_quota" in message:
        return f"AI classification failed due to quota limits. Please check your {provider} account usage."

    return "AI classification failed. Please try again later."


SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def _verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("scrypt$"):
        _, salt_hex, digest_hex = password_hash.split("$", 2)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=SCRYPT_DKLEN,
        )
        return hmac.compare_digest(digest.hex(), digest_hex)

    # legacy unsalted sha256 — constant-time compare, upgraded on next successful login
    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, password_hash)


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


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

# need this otherwise the browser blocks requests from localhost:3000 -> localhost:8000
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


def _persist_ticket(db: Session, user_id: int, ticket: TicketCreate, result) -> Ticket:
    db_ticket = Ticket(
        ticket_code=_generate_unique_ticket_code(db),
        user_id=user_id,
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


@app.post("/tickets", response_model=TicketResponse, status_code=201)
async def create_ticket(ticket: TicketCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # validate -> call LLM -> save to db -> return
    provider = get_llm_provider()

    try:
        result = await provider.triage_ticket(ticket.subject, ticket.description)
    except Exception as e:
        # don't save a half-done ticket if the LLM call fails
        logger.exception("LLM triage failed on create (user_id=%s)", user.id)
        raise HTTPException(
            status_code=502,
            detail=_friendly_llm_error(e),
        )

    return await run_in_threadpool(_persist_ticket, db, user.id, ticket, result)


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


def _check_login_rate_limit(email: str) -> None:
    now = time.time()
    with login_lock:
        recent = [ts for ts in login_attempts[email] if now - ts < LOGIN_WINDOW_SECONDS]
        if len(recent) >= LOGIN_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Please wait a few minutes and try again.",
            )
        recent.append(now)
        login_attempts[email] = recent


@app.post("/auth/login", response_model=AuthResponse)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    email = login_data.email.strip().lower()
    _check_login_rate_limit(email)
    user = db.query(User).filter(User.email == email).first()
    if not user or not _verify_password(login_data.password, user.password_hash):
        logger.warning("Failed login attempt for %s", email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    with login_lock:
        login_attempts.pop(email, None)

    # transparently upgrade legacy unsalted sha256 hashes to scrypt on next login
    if not user.password_hash.startswith("scrypt$"):
        user.password_hash = _hash_password(login_data.password)
        db.add(user)
        db.commit()

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


def _check_regenerate_rate_limit(user_id: int) -> None:
    now = time.time()
    with regenerate_lock:
        recent = [ts for ts in regenerate_attempts[user_id] if now - ts < REGENERATE_WINDOW_SECONDS]
        if len(recent) >= REGENERATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"You can only regenerate replies {REGENERATE_LIMIT} times every 5 minutes.",
            )
        recent.append(now)
        regenerate_attempts[user_id] = recent
        # drop keys that have aged out entirely so the dict can't grow without bound
        for key in [k for k, v in regenerate_attempts.items() if not v]:
            del regenerate_attempts[key]


def _load_user_ticket(db: Session, ticket_id: int, user_id: int) -> Optional[Ticket]:
    return db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user_id).first()


def _save_ticket(db: Session, ticket: Ticket) -> Ticket:
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@app.patch("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket_reply(ticket_id: int, payload: TicketReplyUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = await run_in_threadpool(_load_user_ticket, db, ticket_id, user.id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if payload.regenerate:
        _check_regenerate_rate_limit(user.id)
        provider = get_llm_provider()
        try:
            result = await provider.triage_ticket(ticket.subject, ticket.description)
        except Exception as e:
            logger.exception(
                "LLM triage failed on regenerate (user_id=%s ticket_id=%s)", user.id, ticket_id
            )
            raise HTTPException(status_code=502, detail=_friendly_llm_error(e))
        ticket.suggested_reply = result.reply
    elif payload.reply:
        ticket.suggested_reply = payload.reply

    return await run_in_threadpool(_save_ticket, db, ticket)


@app.get("/analytics", response_model=TicketAnalytics)
def ticket_analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    category_rows = (
        db.query(Ticket.category, sa_func.count(Ticket.id))
        .filter(Ticket.user_id == user.id)
        .group_by(Ticket.category)
        .all()
    )
    priority_rows = (
        db.query(Ticket.priority, sa_func.count(Ticket.id))
        .filter(Ticket.user_id == user.id)
        .group_by(Ticket.priority)
        .all()
    )

    category_counts = {row[0] or "Uncategorized": row[1] for row in category_rows}
    priority_counts = {row[0] or "Unknown": row[1] for row in priority_rows}

    return TicketAnalytics(category_counts=category_counts, priority_counts=priority_counts)
