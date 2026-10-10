"""Dependencias de FastAPI: acceso a los servicios y verificación de sesión."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings
from app.services.auth_service import AuthService
from app.services.redirect_service import RedirectService

SESSION_COOKIE = "ts3proxy_session"


@dataclass
class Container:
    """Servicios creados en el lifespan y guardados en app.state.container."""

    settings: Settings
    auth: AuthService
    redirects: RedirectService


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_settings_dep(c: Annotated[Container, Depends(get_container)]) -> Settings:
    return c.settings


def get_auth_service(c: Annotated[Container, Depends(get_container)]) -> AuthService:
    return c.auth


def get_redirect_service(c: Annotated[Container, Depends(get_container)]) -> RedirectService:
    return c.redirects


def require_session(
    request: Request, auth: Annotated[AuthService, Depends(get_auth_service)]
) -> str:
    user = auth.validate_token(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sesión no válida o caducada")
    return user


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
AuthDep = Annotated[AuthService, Depends(get_auth_service)]
RedirectServiceDep = Annotated[RedirectService, Depends(get_redirect_service)]
CurrentUser = Annotated[str, Depends(require_session)]
