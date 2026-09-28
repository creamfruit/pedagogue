from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, SessionDep, StorageDep, get_user_by_email
from app.core.security import hasher, tokens
from app.models.models import User
from app.schemas.schemas import AccountDeletion, Token, UserLogin, UserRead, UserRegister
from app.services.account import delete_account

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, session: SessionDep) -> Token:
    existing = await get_user_by_email(session, payload.email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="that email is already registered")
    user = User(
        email=payload.email.lower(),
        password_hash=hasher.hash(payload.password),
        display_name=payload.display_name,
    )
    session.add(user)
    await session.flush()
    return Token(access_token=tokens.create_access_token(str(user.id)), expires_in=tokens.expires_in)


@router.post("/login", response_model=Token)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> Token:
    user = await get_user_by_email(session, form.username)
    if user is None or not hasher.verify(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=tokens.create_access_token(str(user.id)), expires_in=tokens.expires_in)


@router.post("/token", response_model=Token)
async def token_login(payload: UserLogin, session: SessionDep) -> Token:
    user = await get_user_by_email(session, payload.email)
    if user is None or not hasher.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="incorrect email or password")
    return Token(access_token=tokens.create_access_token(str(user.id)), expires_in=tokens.expires_in)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_me(payload: AccountDeletion, user: CurrentUser, session: SessionDep, storage: StorageDep) -> Response:
    if payload.confirmation.strip().upper() != "DELETE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="type DELETE to confirm")
    if not hasher.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="that password is incorrect")
    await delete_account(session, user, storage)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
