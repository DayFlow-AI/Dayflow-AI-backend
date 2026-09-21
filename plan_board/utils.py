from enum import Enum

from fastapi import WebSocket, WebSocketException
from fastapi.logger import logger
from fastapi_jwt.jwt_backends import AuthlibJWTBackend
from fastapi_jwt.jwt_backends.abstract_backend import BackendException

from user.utils import sec_key_access

auth_jwt = AuthlibJWTBackend()


async def access_security(
    cookie: dict[str, str],
) -> int | None:
    access_has = cookie.get("access_token_cookie")
    if access_has:
        try:
            user = auth_jwt.decode(access_has, sec_key_access)
            if user:
                if user.get("type") is None or user.get("type") != "access":
                    raise WebSocketException(code=1008, reason="invalid type token")
                return int(user.get("subject", "")["uid"])
            return None
        except BackendException as e:
            logger.exception("access_security failed")
            raise WebSocketException(code=1008, reason="Token failed") from e
    raise WebSocketException(code=1008, reason="Empty credentials")


class StatusCard(Enum):
    completed = "completed"
    in_progress = "in_progress"
    pending = "pending"
    cancelled = "cancelled"
    new = "new"


class CardColor(Enum):
    completed = "#22c55e"
    in_progress = "#3b82f6"
    pending = "#f59e0b"
    cancelled = "#ef4444"
    new = "#64748b"


class ConnectionManager:
    def __init__(self, chat_id: int):
        self.connection = {chat_id: set()}

    async def connect(self, chat_id: int, websocket: WebSocket):
        self.connection[chat_id].add(websocket)
        print(self.connection[chat_id])

    async def disconnect(self, chat_id: int, websocket: WebSocket):
        self.connection[chat_id].discard(websocket)

        if len(self.connection[chat_id]) == 0:
            del self.connection[chat_id]

    async def pool_messages(self, chat_id: int, messages: str):
        for user in self.connection[chat_id]:
            await user.send_text(messages)
