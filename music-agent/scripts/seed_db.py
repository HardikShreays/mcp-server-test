from __future__ import annotations

import sys
from pathlib import Path
from datetime import UTC, datetime

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import SessionLocal
from models import User


SEED_USERS = [
    {"username": "user_a", "password": "user123", "role": "requestor"},
    {"username": "user_b", "password": "user123", "role": "requestor"},
    {"username": "user_d", "password": "user123", "role": "requestor"},
    {"username": "user_e", "password": "user123", "role": "requestor"},
    {"username": "admin1", "password": "admin123", "role": "admin"},
    {"username": "admin2", "password": "admin123", "role": "admin"},
]


def main() -> None:
    db = SessionLocal()
    created = 0
    try:
        existing = {u.username: u for u in db.query(User).all()}
        for item in SEED_USERS:
            row = existing.get(item["username"])
            if row is None:
                row = User(
                    username=item["username"],
                    password_hash=generate_password_hash(item["password"]),
                    role=item["role"],
                    is_active=True,
                    created_at=datetime.now(UTC),
                )
                db.add(row)
                created += 1
            else:
                row.role = item["role"]
                row.is_active = True
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()

    print(f"Seed complete. Created {created} user(s).")


if __name__ == "__main__":
    main()
