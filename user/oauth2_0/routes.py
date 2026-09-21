from asyncio import sleep
from datetime import UTC, datetime

import httpx
from authlib.integrations.base_client import OAuthError
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.logger import logger
from httpx_retries import Retry, RetryTransport
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from db_conf.db import SessionDep
from proj_settings.env_conf import settings
from user.models import UsersORM
from user.oauth2_0.schemas import OauthSchema
from user.oauth2_0.utils import get_google_profile
from user.utils import access_token_conf, gen_jwt, refresh_token_conf

oauth2_router = APIRouter(prefix="/api/oauth2", tags=["oauth2"])

transport = RetryTransport(
    retry=Retry(total=5, backoff_factor=1.0, respect_retry_after_header=True),
    transport=httpx.AsyncHTTPTransport()
)

client = AsyncOAuth2Client(
    client_id=settings.client_id,
    client_secret=settings.client_sec,
    redirect_uri=settings.redirect_uri,
    scope=settings.user_scopes,
    transport=transport,
)


@oauth2_router.post(
    "/auth/callback", status_code=status.HTTP_200_OK, response_model=OauthSchema
)
async def auth_callback(code: OauthSchema, db: SessionDep) -> Response:
    try:
        token = await client.fetch_token(
            "https://oauth2.googleapis.com/token",
            code=code.code,
            grant_type="authorization_code",
        )
        user_data = await get_google_profile(token["access_token"])
        stmt = (
            insert(UsersORM)
            .values(
                username=user_data.name,
                email=user_data.email,
                google_sub=user_data.sub,
                oauth=True,
                google_refresh_token=token["refresh_token"],
            )
            .on_conflict_do_update(
                index_elements=["google_sub"],
                set_={
                    "username": user_data.name,
                    "email": user_data.email,
                    "google_refresh_token": token["refresh_token"],
                    "updated_at": datetime.now(tz=UTC),
                },
            )
            .returning(UsersORM.id)
        )
        result = await db.execute(stmt)
        result = result.scalar_one()
        user = select(UsersORM).where(UsersORM.id == result)
        result = await db.execute(user)
        result = result.scalar_one()
        jwt = await gen_jwt(result, db, True)
        response = Response(status_code=status.HTTP_200_OK)
        response.set_cookie(**access_token_conf(jwt["access_token"]))
        response.set_cookie(**refresh_token_conf(jwt["refresh_token"]))

    except OAuthError as e:
        await db.rollback()
        logger.info("OAuthError info: %s", e.description)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="error: OAuth authentication failed",
        )

    except ValidationError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Validation Error"
        )

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error("SQL mistakes: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Other mistakes"
        )

    except httpx.ConnectTimeout as e:
        await db.rollback()
        logger.error("Connection timeout: %s", e)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Google service overload",
        )

    else:
        return response
