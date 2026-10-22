from fastapi import APIRouter, HTTPException
from fastapi.logger import logger
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import ResourceClosedError, SQLAlchemyError

from db_conf.db import SessionDep
from global_utils import AccessCredentials, ErrorResponse
from plan_board.models import ChatORM
from plan_board.schemas import ChatCreateSchema, ChatSchema, ListChatOutSchema

plan_board_router = APIRouter(prefix="/api/board", tags=["PlanBoard"])


@plan_board_router.post(
    "/add_board",
    response_model=ChatSchema,
    responses={
        500: {"description": "Server Error"},
        401: {"description": "Unauthorized", "model": ErrorResponse},
        404: {"description": "Not Found"},
    },
)
async def add_board(
    db: SessionDep, credentials: AccessCredentials, incoming_data: ChatCreateSchema
) -> ChatSchema:

    try:
        answer = (
            await db.execute(
                insert(ChatORM)
                .values(title=incoming_data.title, owner_id=int(credentials["uid"]))
                .returning(ChatORM.id, ChatORM.title)
            )
        ).first()
        await db.commit()
    except SQLAlchemyError as e:
        logger.error(e)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Server Side Error")

    return ChatSchema.model_validate(answer)


@plan_board_router.get(
    "/get_boards",
    response_model=ListChatOutSchema,
    responses={
        500: {"description": "Server Error"},
        401: {"description": "Unauthorized", "model": ErrorResponse},
    },
)
async def get_boards(
    db: SessionDep, credentials: AccessCredentials
) -> ListChatOutSchema:
    try:
        answer = (
            (
                await db.execute(
                    select(ChatORM).where(ChatORM.owner_id == int(credentials["uid"]))
                )
            )
            .scalars()
            .all()
        )
        if answer is None:
            answer = []
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(e)
        raise HTTPException(status_code=500, detail="Server Side Error")
    else:
        return ListChatOutSchema(chats=answer)


@plan_board_router.put(
    "/update_board",
    response_model=ChatSchema,
    responses={
        500: {"description": "Server Error"},
        401: {"description": "Unauthorized", "model": ErrorResponse},
    },
)
async def update_board(
    db: SessionDep, credentials: AccessCredentials, incoming_data: ChatSchema
):

    try:
        answer = (
            await db.execute(
                update(ChatORM)
                .where(
                    ChatORM.owner_id == int(credentials["uid"]),
                    ChatORM.id == incoming_data.id,
                )
                .values(title=incoming_data.title)
                .returning(ChatORM)
            )
        ).scalar_one()
        await db.commit()

    except ResourceClosedError:
        await db.rollback()
        raise HTTPException(status_code=404, detail="Nothing to change")

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(e)
        raise HTTPException(status_code=500, detail="Server Side Error")

    else:
        return ChatSchema.model_validate(answer).model_dump()
