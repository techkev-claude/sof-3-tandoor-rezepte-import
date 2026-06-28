import os
from typing import Optional
import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlmodel import Session, select
from app.models import User, engine

SECRET_KEY = os.getenv("SECRET_KEY", "changeme-secret")
serializer = URLSafeTimedSerializer(SECRET_KEY)
SESSION_COOKIE = "session_token"
MAX_AGE = 86400  # 24h


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_session_token(username: str) -> str:
    return serializer.dumps(username)


def verify_session_token(token: str) -> Optional[str]:
    try:
        return serializer.loads(token, max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def create_default_user():
    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD", "changeme")
    with Session(engine) as session:
        existing = session.exec(select(User)).first()
        if not existing:
            user = User(username=admin_user, hashed_password=hash_password(admin_pass))
            session.add(user)
            session.commit()


def get_current_user(request) -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return verify_session_token(token)
