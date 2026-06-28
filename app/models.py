import os
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session, select

DB_PATH = os.getenv("DB_PATH", "/app/data/db.sqlite3")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str


class Settings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tandoor_url: str = Field(default="")
    tandoor_api_key: str = Field(default="")
    ai_provider: str = Field(default="openai")
    ai_api_key: str = Field(default="")
    ai_model: str = Field(default="gpt-4o")
    ollama_base_url: str = Field(default="http://localhost:11434")


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
