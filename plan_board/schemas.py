from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ChatSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str


class ChatCreateSchema(BaseModel):
    title: str


class ListChatOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    chats: list[ChatSchema] = Field(default_factory=list)


class StatusCard(Enum):
    completed = "completed"
    in_progress = "in_progress"
    pending = "pending"
    cancelled = "cancelled"
    new = "new"


class CardLinkSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int = None


class CardSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    chat_id: int
    pos_x: float = 0.0
    pos_y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    status: StatusCard = "new"
    color: str = "#ffffff"
    title: str = Field(max_length=50)
    text: str
    links: list[CardLinkSchema] = []


class CardOutSchema(CardSchema):
    id: int


class CardDeleteSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: list[int] = Field(default_factory=list)
