from fastapi import APIRouter, HTTPException, Response, status
from fastapi.logger import logger
from sqlalchemy import delete, exists, or_, select
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from db_conf.db import SessionDep
from global_utils import AccessCredentials, RefreshCredentials
from user.models import UsersJWTStorageORM, UsersORM
from user.schemas import (
    AuthSuccessSchema,
    ChangePasswordSchema,
    PasswordResponseSchema,
    UserLoginSchema,
    UserPublicSchema,
    UserRegisterSchema,
)
from user.utils import (
    access_token_conf,
    gen_jwt,
    password_hash,
    refresh_token_conf,
    user_compile,
)

user_router = APIRouter(prefix="/api/user", tags=["user"])


@user_router.post(
    "/register",
    summary="create and auth user",
    response_model=AuthSuccessSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "user already exists"},
    },
)
async def register(user: UserRegisterSchema, db: SessionDep) -> Response:
    query = select(
        exists().where(
            or_(UsersORM.email == user.email, UsersORM.username == user.username)
        )
    )
    exists_result = (await db.execute(query)).scalar()
    if not exists_result:
        new_user = await user_compile(user, db)
        jwt = await gen_jwt(new_user, db, True)
        response = Response(status_code=status.HTTP_201_CREATED)
        response.set_cookie(**access_token_conf(jwt["access_token"]))
        response.set_cookie(**refresh_token_conf(jwt["refresh_token"]))
        return response
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Email or username already registered",
    )


@user_router.post(
    "/login",
    summary="Login a user",
    response_model=AuthSuccessSchema,
    responses={
        401: {"description": "Incorrect password"},
        400: {"description": "Incorrect email or username"},
    },
)
async def login_user(login: UserLoginSchema, db: SessionDep) -> Response:
    query = select(UsersORM).where(
        or_(UsersORM.email == login.login, UsersORM.username == login.login)
    )
    exists_login = (await db.execute(query)).scalar()
    if exists_login:
        access = password_hash.verify(login.password, exists_login.password)
        if access:
            jwt = await gen_jwt(exists_login, db, True)
            response = Response(status_code=status.HTTP_200_OK)
            response.set_cookie(**access_token_conf(jwt["access_token"]))
            response.set_cookie(**refresh_token_conf(jwt["refresh_token"]))
            return response
        raise HTTPException(status_code=401, detail="Incorrect password")
    raise HTTPException(status_code=400, detail="Incorrect email or username")


@user_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "no content"},
        401: {"description": "not authorized / session expired"},
    },
)
async def logout(db: SessionDep, credentials: AccessCredentials) -> Response:
    await db.execute(
        delete(UsersJWTStorageORM).where(
            UsersJWTStorageORM.refresh_jti == credentials.jti
        )
    )
    await db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(**access_token_conf(delt=True))
    response.set_cookie(**refresh_token_conf(delt=True))
    return response


@user_router.post(
    "/logout_from_all_devices",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "no content"},
        401: {"description": "not authorized / session expired"},
    },
)
async def logout_from_all_devices(
    db: SessionDep, credentials: AccessCredentials
) -> Response:
    user_id = int(credentials.subject["uid"])
    await db.execute(
        delete(UsersJWTStorageORM).where(UsersJWTStorageORM.user_id == user_id)
    )
    await db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(**access_token_conf(delt=True))
    response.set_cookie(**refresh_token_conf(delt=True))
    return response


@user_router.get(
    "/me",
    response_model=UserPublicSchema,
    status_code=status.HTTP_200_OK,
    summary="get current user",
    response_description="Authorized: user data. 401 - not authorized/session expired",
    responses={401: {"description": "not authorized / session expired"}},
)
async def me(db: SessionDep, credentials: AccessCredentials) -> UserPublicSchema:
    try:
        user = await db.get(UsersORM, int(credentials.subject["uid"]))
    except SQLAlchemyError as e:
        logger.error(f"Me check error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User Does Not Exist"
        )
    return UserPublicSchema.model_validate(user)


@user_router.get(
    "/refresh",
    response_description="Refresh token check",
    description="check refresh token and create new credential if possible",
    responses={
        200: {"description": "refresh token recreated"},
        401: {"description": "not authorized / session expired"},
    },
)
async def refresh(db: SessionDep, credentials: RefreshCredentials):
    try:
        token_record = (
            await db.execute(
                select(UsersJWTStorageORM).where(
                    UsersJWTStorageORM.user_id == int(credentials.subject["uid"]),
                    UsersJWTStorageORM.refresh_jti == credentials.jti,
                )
            )
        ).scalar_one_or_none()

        if token_record is None:
            raise HTTPException(status_code=401, detail="Refresh token not found")

        jwt = await gen_jwt(token_record.user_id, db)
        logger.info("Generated new ACCESS TOKEN")
        response = Response(status_code=status.HTTP_200_OK)
        response.set_cookie(**access_token_conf(jwt["access_token"]))
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Refresh check error: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired")
    else:
        return response


@user_router.post(
    "/change_password",
    status_code=status.HTTP_201_CREATED,
    response_model=PasswordResponseSchema,
    description="Change password and remove credentials if changed",
    tags=["user_management"],
)
async def change_password(
    db: SessionDep, credentials: AccessCredentials, income_data: ChangePasswordSchema
):
    if (income_data.new_password or income_data.current_password) is None:
        raise HTTPException(status_code=400, detail="Incorrect password")
    try:
        user_to_change = await db.get(UsersORM, int(credentials.subject["uid"]))
        if not user_to_change:
            raise HTTPException(status_code=404, detail="User Does Not Exist")
        access = password_hash.verify(
            income_data.current_password, user_to_change.password
        )
        if not access:
            raise HTTPException(status_code=400, detail="Incorrect password")
        if income_data.new_password == income_data.current_password:
            raise HTTPException(status_code=400, detail="New Password is same")
        user_to_change.password = password_hash.hash(income_data.new_password)
        await db.execute(
            delete(UsersJWTStorageORM).where(
                UsersJWTStorageORM.user_id == int(credentials.subject["uid"])
            )
        )
    except SQLAlchemyError as e:
        logger.error(f"Change password error: {e}")
        raise HTTPException(status_code=500, detail="Can`t change password")
    except HTTPException:
        raise
    else:
        await db.commit()
        response = JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"detail": "Password changed successfully, please log in again"},
        )
        response.set_cookie(**access_token_conf(delt=True))
        response.set_cookie(**refresh_token_conf(delt=True))
        return response
