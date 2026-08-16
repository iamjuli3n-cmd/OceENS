from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlmodel import SQLModel, create_engine, Session, select

from models import User
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_DIR = PROJECT_ROOT / "data"
RAW_DATABASE_PATH = os.getenv("LOCAL_DATABASE_DIR")

if RAW_DATABASE_PATH:
    DATABASE_PATH = Path(RAW_DATABASE_PATH).expanduser()
    if not DATABASE_PATH.is_absolute():
        DATABASE_PATH = (PROJECT_ROOT / DATABASE_PATH).resolve()
else:
    DATABASE_PATH = DEFAULT_DATABASE_DIR.resolve()

DATABASE_PATH.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{(DATABASE_PATH / 'db_oceens.db').resolve().as_posix()}"

# check_same_thread is only needed for SQLite
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

def create_db_and_tables():
    """Creates all tables defined in SQLModel."""
    SQLModel.metadata.create_all(engine)

def get_session() -> Session:
    """Dependency for FastAPI to provide a database session."""
    with Session(engine) as session:
        yield session

# Type alias for easier use in FastAPI endpoints
SessionDep = Annotated[Session, Depends(get_session)]

def get_or_create_user(email: str) -> str:
    """
    Retrieves a user's role or creates a new user with default 'student' role.
    
    Args:
        session: The active database session (passed from FastAPI)
        email: User email address
    """
    email = email.strip().lower()
    
    # 1. Search for user using modern SQLModel syntax
    statement = select(User).where(User.mail == email)
    with Session(engine) as session:
        user = session.exec(statement).first()

        if not user:
            # 2. Create if not found
            user = User(mail=email)
            session.add(user)
            session.commit()
            session.refresh(user)
        
        return user