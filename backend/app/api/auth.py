from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import SESSION_COOKIE, AuthDep, CurrentUser, SettingsDep
from app.schemas.auth import LoginIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    # Caddy añade X-Forwarded-For; la API solo escucha en 127.0.0.1 detrás de Caddy.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, request: Request, response: Response, auth: AuthDep, settings: SettingsDep) -> UserOut:
    ip = _client_ip(request)
    retry = auth.throttle.retry_after(ip)
    if retry:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Prueba de nuevo en {retry // 60 + 1} min.",
            headers={"Retry-After": str(retry)},
        )
    if not await auth.verify(body.username, body.password):
        auth.throttle.failure(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")

    auth.throttle.success(ip)
    response.set_cookie(
        SESSION_COOKIE,
        auth.issue_token(),
        max_age=auth.max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )
    return UserOut(username=body.username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, settings: SettingsDep) -> Response:
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, secure=settings.session_cookie_secure, samesite="strict"
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(username=user)
