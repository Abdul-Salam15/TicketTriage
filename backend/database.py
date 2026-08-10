from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv, find_dotenv


dotenv_path = find_dotenv()
if not dotenv_path:
    potential = os.path.join(os.path.dirname(__file__), "venv", ".env")
    if os.path.exists(potential):
        dotenv_path = potential

if dotenv_path:
    load_dotenv(dotenv_path)
else:
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tickets.db")


engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
