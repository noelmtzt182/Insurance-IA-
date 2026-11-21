"""Autenticación del panel privado.

Hash de contraseñas: PBKDF2-HMAC-SHA256 con sal aleatoria de 16 bytes y
390,000 iteraciones (recomendación OWASP), usando solo la biblioteca estándar.

Generar un hash desde la terminal:
    python -m services.auth "MiContraseñaSegura"
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sys
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from utils.config import get_secret, now_mx
from database.models import User

ALGO = "pbkdf2_sha256"
ITERATIONS = 390_000
MIN_PASSWORD_LEN = 10


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGO}${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LEN:
        problems.append(f"Debe tener al menos {MIN_PASSWORD_LEN} caracteres.")
    if password.lower() == password or password.upper() == password:
        problems.append("Combina mayúsculas y minúsculas.")
    if not any(ch.isdigit() for ch in password):
        problems.append("Incluye al menos un número.")
    return problems


def user_count(s: Session) -> int:
    return s.scalar(select(func.count(User.id))) or 0


def create_user(s: Session, username: str, password: str, role: str = "asesor") -> User:
    username = (username or "").strip().lower()
    if len(username) < 3:
        raise ValueError("El usuario debe tener al menos 3 caracteres.")
    problems = password_problems(password)
    if problems:
        raise ValueError(" ".join(problems))
    if s.scalar(select(User).where(User.username == username)):
        raise ValueError("Ese usuario ya existe.")
    user = User(username=username, password_hash=hash_password(password), role=role)
    s.add(user)
    s.flush()
    return user


def change_password(s: Session, username: str, current: str, new: str) -> None:
    user = s.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(current, user.password_hash):
        raise ValueError("La contraseña actual no es correcta.")
    problems = password_problems(new)
    if problems:
        raise ValueError(" ".join(problems))
    user.password_hash = hash_password(new)
    s.flush()


def users_df(s: Session):
    import pandas as pd
    rows = s.scalars(select(User).order_by(User.username)).all()
    return pd.DataFrame([{"Usuario": u.username, "Rol": u.role, "Creado": u.created_at, "Último acceso": u.last_login}
                         for u in rows], columns=["Usuario", "Rol", "Creado", "Último acceso"])


def bootstrap_admin_from_secrets(s: Session) -> Optional[str]:
    """Crea/actualiza el administrador definido en st.secrets [auth].

    [auth]
    admin_username = "admin"
    admin_password_hash = "pbkdf2_sha256$390000$..."
    """
    username = get_secret("admin_username", section="auth")
    pw_hash = get_secret("admin_password_hash", section="auth")
    if not username or not pw_hash or not str(pw_hash).startswith(ALGO + "$"):
        return None
    username = str(username).strip().lower()
    user = s.scalar(select(User).where(User.username == username))
    if user is None:
        s.add(User(username=username, password_hash=str(pw_hash), role="admin"))
    elif user.password_hash != pw_hash:
        user.password_hash = str(pw_hash)
        user.role = "admin"
    s.flush()
    return username


def authenticate(s: Session, username: str, password: str) -> Optional[User]:
    username = (username or "").strip().lower()
    user = s.scalar(select(User).where(User.username == username))
    if user is None:
        # Igualar tiempo de respuesta para no revelar si el usuario existe
        verify_password(password or "", hash_password("dummy-password", iterations=ITERATIONS))
        return None
    if not verify_password(password or "", user.password_hash):
        return None
    user.last_login = now_mx()
    s.flush()
    return user


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) != 2:
        print('Uso: python -m services.auth "TuContraseñaSegura"')
        sys.exit(1)
    pw = sys.argv[1]
    issues = password_problems(pw)
    if issues:
        print("Advertencia:", " ".join(issues))
    print(hash_password(pw))
