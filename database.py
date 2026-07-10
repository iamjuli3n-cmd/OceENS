from typing import Annotated
from fastapi import Depends
from sqlmodel import SQLModel, create_engine, Session, select
# Assuming User is defined in models.py inheriting from SQLModel
from models import User 

DATABASE_URL = "sqlite:///./database/db_oceens.db"

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

def get_or_create_user(session: Session, email: str) -> str:
    """
    Retrieves a user's role or creates a new user with default 'student' role.
    
    Args:
        session: The active database session (passed from FastAPI)
        email: User email address
    """
    email = email.strip().lower()
    
    # 1. Search for user using modern SQLModel syntax
    statement = select(User).where(User.mail == email)
    user = session.exec(statement).first()

    if not user:
        # 2. Create if not found
        user = User(mail=email)
        session.add(user)
        session.commit()
        session.refresh(user)
    
    return user