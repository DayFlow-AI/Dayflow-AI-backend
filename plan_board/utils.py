from collections import defaultdict
from typing import Any

from fastapi import WebSocket, WebSocketException
from fastapi_jwt.jwt_backends import AuthlibJWTBackend
from fastapi_jwt.jwt_backends.abstract_backend import BackendException
from starlette.websockets import WebSocketDisconnect

from user.utils import sec_key_access

auth_jwt = AuthlibJWTBackend()


async def access_security(
    websocket: WebSocket,
) -> int | None:
    access_has = websocket.cookies.get("access_token_cookie")
    if not access_has:
        return None

    try:
        user = auth_jwt.decode(access_has, sec_key_access)
    except BackendException as e:
        await websocket.close(code=1008, reason="Token failed")
        raise WebSocketDisconnect(code=1008, reason="Token failed") from e

    if not user or user.get("type") != "access":
        raise WebSocketException(code=1008, reason="invalid token")
    subject = user.get("subject") or {}
    if "uid" not in subject:
        raise WebSocketException(code=1008, reason="token has no uid")

    return int(subject["uid"])


class ConnectionManager:
    def __init__(self):
        self._connections: defaultdict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: int, websocket: WebSocket):
        self._connections[user_id].add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket):
        sockets = self._connections.get(user_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            del self._connections[user_id]

    async def pool_messages(self, user_id: int, messages: Any):
        for ws in self._connections[user_id]:
            await ws.send_json(messages)
