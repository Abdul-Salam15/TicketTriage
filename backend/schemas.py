from pydantic import BaseModel, field_validator, model_validator
from typing import Optional
from datetime import datetime


class TicketCreate(BaseModel):
    subject: str
    description: str

    @field_validator("subject", "description")
    @classmethod
    def not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("This field cannot be empty")
        return value.strip()


class TicketResponse(BaseModel):
    id: int
    ticket_code: str
    subject: str
    description: str
    category: Optional[str]
    priority: Optional[str]
    suggested_reply: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserAuth(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or "." not in email:
            raise ValueError("Please enter a valid email address")
        return email

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Password is required")
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in value):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in value):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in value):
            raise ValueError("Password must contain at least one number")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/`~" for c in value):
            raise ValueError("Password must contain at least one special character (!@#$%^&*...)")
        return value


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    user: UserResponse
    token: str


class TriageResult(BaseModel):
    # what we expect back from the LLM — category, priority, and a draft reply
    category: str
    priority: str
    reply: str


class TicketReplyUpdate(BaseModel):
    reply: Optional[str] = None
    regenerate: bool = False

    @field_validator("reply", mode="before")
    @classmethod
    def normalize_reply(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def validate_update(self):
        if not self.reply and not self.regenerate:
            raise ValueError("Either reply or regenerate must be provided")
        return self


class TicketAnalytics(BaseModel):
    category_counts: dict[str, int]
    priority_counts: dict[str, int]
