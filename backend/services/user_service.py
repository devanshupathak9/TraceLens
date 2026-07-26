"""
User registration and login.

The service owns the logic and raises its own exceptions; the router's only job
is translating them into HTTP status codes. That keeps HTTP concerns out of
here, so the same service works from a test or a script without FastAPI.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from schemas import RegisterRequest
from security import hash_password, verify_password


class EmailAlreadyRegistered(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        # Emails are stored lowercased, so lookups lowercase too — otherwise
        # User@x.com and user@x.com become two different accounts.
        result = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def register(self, data: RegisterRequest) -> User:
        if await self.get_by_email(data.email) is not None:
            raise EmailAlreadyRegistered

        user = User(
            name=data.name,
            email=data.email.lower(),
            password_hash=hash_password(data.password),
        )
        self.session.add(user)

        try:
            await self.session.commit()
        except IntegrityError:
            # Two requests registering the same email at the same time both pass
            # the check above; the unique constraint catches the loser here.
            await self.session.rollback()
            raise EmailAlreadyRegistered

        await self.session.refresh(user)
        return user

    async def login(self, email: str, password: str) -> User:
        user = await self.get_by_email(email)

        # One error for "no such email" and "wrong password" — telling them
        # apart lets an attacker probe which emails have accounts.
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentials

        return user
