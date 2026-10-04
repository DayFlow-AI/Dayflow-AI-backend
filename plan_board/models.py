from sqlalchemy import (
    CheckConstraint,
    Column,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db_conf.db import Base
from plan_board.schemas import StatusCard
from user.models import UsersORM


class ChatORM(Base):
    __tablename__ = "chat_orm"
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    owner: Mapped[UsersORM] = relationship()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    cursor_x: Mapped[float] = mapped_column(Float, default=0.0)
    cursor_y: Mapped[float] = mapped_column(Float, default=0.0)
    cards: Mapped[list[CardORM]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
    )


class CardORM(Base):
    __tablename__ = "card_orm"
    chat_id: Mapped[int] = mapped_column(ForeignKey("chat_orm.id"), index=True)
    chat: Mapped[ChatORM] = relationship(back_populates="cards")
    links: Mapped[list[CardORM]] = relationship(
        secondary="card_links",
        primaryjoin="CardORM.id == card_links.c.from_card_id",
        secondaryjoin="CardORM.id == card_links.c.to_card_id",
    )

    pos_x: Mapped[float] = mapped_column(Float, default=0.0)
    pos_y: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[float] = mapped_column(
        Float, CheckConstraint("width >= 0"), default=0.0
    )
    height: Mapped[float] = mapped_column(
        Float, CheckConstraint("height >= 0"), default=0.0
    )
    status: Mapped[StatusCard] = mapped_column(
        Enum(StatusCard, values_callable=lambda e: [x.value for x in e]),
        default=StatusCard.new,
        server_default=StatusCard.new.value,
        nullable=False,
    )
    color: Mapped[str] = mapped_column(default="#ffffff")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="empty")


card_manager = Table(
    "card_links",
    Base.metadata,
    Column(
        "from_card_id",
        Integer,
        ForeignKey("card_orm.id", ondelete="CASCADE"),
        index=True,
    ),
    Column(
        "to_card_id", Integer, ForeignKey("card_orm.id", ondelete="CASCADE"), index=True
    ),
    CheckConstraint("from_card_id <> to_card_id", name="ck_no_self_link"),
    UniqueConstraint("from_card_id", "to_card_id", name="uq_card_link"),
)
