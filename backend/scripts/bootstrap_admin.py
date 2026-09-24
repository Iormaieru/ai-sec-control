"""Creates the first admin user directly against the DB, bypassing the API.

Needed because POST /auth/register itself requires an existing admin's JWT
— without this script there would be no way to create the very first user.
Run once per environment: `uv run python scripts/bootstrap_admin.py`.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.models import UserRole  # noqa: E402
from app.auth.service import create_user, get_user_by_username  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", default=None)
    args = parser.parse_args()

    # Sin terminal (ej. un Cloud Run Job) no hay a quién pedirle la
    # contraseña: se toma de AISEC_BOOTSTRAP_ADMIN_PASSWORD, que debería
    # venir de un secreto y no quedar en el historial de un shell.
    password = os.environ.get("AISEC_BOOTSTRAP_ADMIN_PASSWORD")
    if password is None:
        password = getpass.getpass("Contraseña para el admin: ")
        confirm = getpass.getpass("Confirmar contraseña: ")
        if password != confirm:
            print("Las contraseñas no coinciden.", file=sys.stderr)
            raise SystemExit(1)

    db = SessionLocal()
    try:
        if get_user_by_username(db, args.username) is not None:
            print(f"El usuario '{args.username}' ya existe.", file=sys.stderr)
            raise SystemExit(1)
        user = create_user(
            db, username=args.username, password=password, full_name=args.full_name, role=UserRole.ADMIN
        )
        print(f"Admin '{user.username}' creado con id {user.id}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
