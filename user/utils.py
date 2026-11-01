from time import time
from uuid import uuid4

from fastapi import HTTPException
from fastapi_jwt import JwtAccessBearerCookie, JwtRefreshCookie
from fastapi_jwt.jwt_backends import AuthlibJWTBackend
from fastapi_jwt.jwt_backends.abstract_backend import BackendException
from pwdlib import PasswordHash
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from db_conf.db import SessionDep
from proj_settings.env_conf import settings
from user.models import UsersJWTStorageORM, UsersORM
from user.schemas import UserRegisterSchema

sec_key_access = settings.jwt_secret_key
sec_key_refresh = settings.jwt_secret_refresh_key
password_hash = PasswordHash.recommended()
access_security = JwtAccessBearerCookie(secret_key=sec_key_access)
refresh_security = JwtRefreshCookie(secret_key=sec_key_refresh)
auth_jwt = AuthlibJWTBackend()


def access_token_conf(access_token: str) -> dict:
    return {
        "key": "access_token_cookie",
        "value": access_token,
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "domain": settings.cookie_domain or None,
        "max_age": 900,
        "path": "/",
    }


def refresh_token_conf(refresh_token: str = "", delete: bool = False) -> dict:
    return {
        "key": "refresh_token_cookie",
        "value": refresh_token,
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "domain": settings.cookie_domain or None,
        "max_age": -1 if delete else 2678400,
        "path": "/api/user/refresh",
    }


async def user_compile(user: UserRegisterSchema, db: SessionDep) -> UsersORM:
    try:
        hashed = password_hash.hash(user.password)
        new_user = UsersORM(username=user.username, email=user.email, password=hashed)
        db.add(new_user)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    return new_user


async def gen_jwt(
    hashed_user: UsersORM, db: SessionDep, with_refresh: bool = False
) -> dict[str, str]:
    try:
        hashed_user = hashed_user.id if with_refresh else hashed_user
        jti_refresh = str(uuid4()) if with_refresh else None
        jti_access = str(uuid4())

        refresh_token = (
            refresh_security.create_refresh_token(
                subject={"uid": str(hashed_user)},
                unique_identifier=jti_refresh,
            )
            if jti_refresh
            else None
        )
        access_token = access_security.create_access_token(
            subject={"uid": str(hashed_user)},
            unique_identifier=jti_access,
        )
        if refresh_token:
            exp = auth_jwt.decode(refresh_token, sec_key_refresh).get("exp")
            await db.execute(
                delete(UsersJWTStorageORM).where(
                    UsersJWTStorageORM.user_id == hashed_user,
                    UsersJWTStorageORM.exp < time(),
                )
            )
            db.add(
                UsersJWTStorageORM(
                    user_id=hashed_user, refresh_jti=jti_refresh, exp=exp
                )
            )
        await db.commit()
        if refresh_token:
            return {"access_token": access_token, "refresh_token": refresh_token}
        return {"access_token": access_token}
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Cannot create new jwt")
    except BackendException as e:
        raise HTTPException(status_code=401, detail=str(e))
