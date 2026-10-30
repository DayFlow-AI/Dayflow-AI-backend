from typing import Any

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
)
from fastapi.logger import logger
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from uvicorn.protocols.utils import ClientDisconnected

from db_conf.db import AsyncSession, SessionDep
from plan_board.models import CardORM, ChatORM, card_links
from plan_board.schemas import (
    CardLinkerSchema,
    CardOutSchema,
    CardSchema,
    CardWithLinkSchema,
    GroupDeleteSchema,
)
from plan_board.utils import ConnectionManager, access_security

ws_router = APIRouter()
manager = ConnectionManager()


async def _handle_command(
    command: dict[str, Any],
    db: AsyncSession,
    chat_id: int,
) -> dict[str, Any]:
    match command.get("mode"):
        case "get_state":
            cards = (
                (
                    await db.execute(
                        select(CardORM)
                        .options(selectinload(CardORM.links))
                        .where(CardORM.chat_id == chat_id)
                    )
                )
                .scalars()
                .all()
            )
            return {
                "message": [
                    CardWithLinkSchema.model_validate(c).model_dump(mode="json")
                    for c in cards
                ],
            }
        case "new_card":
            new_card = (
                await db.execute(
                    insert(CardORM)
                    .values(
                        **CardSchema.model_validate(command.get("body")).model_dump()
                    )
                    .returning(CardORM)
                )
            ).scalar_one()
            return {
                "message": CardOutSchema.model_validate(new_card).model_dump(
                    mode="json"
                ),
            }
        case "delete_card":
            del_list = GroupDeleteSchema.model_validate(command.get("body"))
            await db.execute(
                delete(CardORM).where(
                    CardORM.id.in_(del_list.id), CardORM.chat_id == chat_id
                )
            )
            return {"message": f"cards {del_list!r} deleted"}
        case "link_card":
            card_link = CardLinkerSchema.model_validate(command.get("body"))
            await db.execute(
                insert(card_links).values(
                    from_card_id=card_link.from_card_id, to_card_id=card_link.to_card_id
                )
            )
            return {
                "message": f"card {card_link.from_card_id} linked to {card_link.to_card_id}"
            }
        case _:
            return {"error": f"unknown command {command.get('mode')!r}"}


@ws_router.websocket("/wss/{chat_id}")
async def websocket_endpoint(
    websocket: WebSocket, db: SessionDep, chat_id: int
) -> None:
    await websocket.accept()
    user_id: int | None = None
    try:
        try:
            user_id = await access_security(websocket)
        except WebSocketException as exc:
            await websocket.close(code=exc.code, reason=exc.reason)
            return

        if not user_id:
            await websocket.close(code=1008, reason="unauthorized")
            return

        await manager.connect(user_id, websocket)

        chat = (
            await db.execute(
                select(ChatORM).where(
                    ChatORM.owner_id == user_id, ChatORM.id == chat_id
                )
            )
        ).scalar_one_or_none()
        # username = (
        #     await db.execute(
        #         select(UsersORM.username).where(
        #             UsersORM.id == user_id
        #         )
        #     )
        # ).scalar_one_or_none()
        if chat is None:
            await websocket.close(code=1008, reason="unauthorized")
            raise WebSocketDisconnect(code=1008, reason="unauthorized")

        chat_title = chat.title

        await websocket.send_json(
            {"type": "connected", "chat_id": chat_id, "title": chat_title}
        )

        while True:
            try:
                command = await websocket.receive_json()
                answer = await _handle_command(command, db, chat_id)
                await db.commit()
                await websocket.send_json(answer)

            except SQLAlchemyError as e:
                await db.rollback()
                logger.exception("ws %s db error: %s", user_id, e)
                await websocket.send_json({"error": "db error check your data"})

            except WebSocketDisconnect:
                logger.info("ws %s disconnected", user_id)
                break

            except ClientDisconnected:
                logger.info("ws %s client gone", user_id)
                break

            except ValidationError as e:
                await db.rollback()
                logger.exception("ws %s pydantic error: %s", user_id, e.__dict__)
                message = {
                    i["loc"][0]: "is_missing"
                    for i in e.errors()
                    if i["type"] == "missing"
                }
                if not message:
                    await websocket.send_json(
                        {"message": "error data validation, check your data"}
                    )
                await websocket.send_json({"message": message})

    except WebSocketException, WebSocketDisconnect:
        logger.info("ws handshake aborted for %s", user_id)

    except SQLAlchemyError as e:
        await db.rollback()
        logger.exception("ws handshake db error: %s", e)
        await websocket.close(code=1011, reason="db error")

    finally:
        if user_id:
            await manager.disconnect(user_id, websocket)
