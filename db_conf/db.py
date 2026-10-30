from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from proj_settings.env_conf import settings

db_pass = settings.db_pass
db_user = settings.db_user
db_schema = settings.db_schema
db_host = settings.db_host

if not all([db_user, db_pass, db_schema]):
    raise RuntimeError("environment variables not set check env file")

db_url = f"postgresql+psycopg://{db_user}:{db_pass}@{db_host}:5432/{db_schema}"
engine = create_async_engine(db_url, connect_args={"connect_timeout": 3})

new_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with new_session() as conn:
        yield conn


SessionDep = Annotated[AsyncSession, Depends(get_session)]


class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
