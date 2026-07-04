"""
Promote a user to admin role.

Usage:
    cd backend && python scripts/create_admin.py user@example.com
"""
import asyncio
import sys

from sqlalchemy import select, update

# Ensure the backend app is importable
sys.path.insert(0, ".")

from app.database import engine
from app.models.user import User  # noqa: E402


async def promote(email: str):
    async with engine.begin() as conn:
        result = await conn.execute(select(User).where(User.email == email))
        user = result.mappings().first()
        if not user:
            print(f"ERROR: No user found with email '{email}'")
            return False

        if user["role"] == "admin":
            print(f"'{email}' is already an admin.")
            return True

        await conn.execute(
            update(User).where(User.email == email).values(role="admin")
        )
        print(f"OK: '{email}' promoted to admin.")
        return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/create_admin.py <email>")
        sys.exit(1)
    ok = asyncio.run(promote(sys.argv[1]))
    sys.exit(0 if ok else 1)
