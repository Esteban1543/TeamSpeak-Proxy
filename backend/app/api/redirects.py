from fastapi import APIRouter, status

from app.api.deps import CurrentUser, RedirectServiceDep, SettingsDep
from app.schemas.redirects import PortUsageOut, RedirectCreate, RedirectOut

router = APIRouter(prefix="/api", tags=["redirects"])


@router.get("/redirects", response_model=list[RedirectOut])
async def list_redirects(_: CurrentUser, service: RedirectServiceDep, settings: SettingsDep) -> list[RedirectOut]:
    return [RedirectOut.from_view(v, settings.public_host) for v in await service.list()]


@router.post("/redirects", response_model=RedirectOut, status_code=status.HTTP_201_CREATED)
async def create_redirect(
    body: RedirectCreate, _: CurrentUser, service: RedirectServiceDep, settings: SettingsDep
) -> RedirectOut:
    view = await service.create(body.target)
    return RedirectOut.from_view(view, settings.public_host)


@router.delete("/redirects/{redirect_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_redirect(redirect_id: int, _: CurrentUser, service: RedirectServiceDep) -> None:
    await service.delete(redirect_id)


@router.get("/ports/usage", response_model=PortUsageOut)
async def port_usage(_: CurrentUser, service: RedirectServiceDep, settings: SettingsDep) -> PortUsageOut:
    return PortUsageOut.from_usage(await service.port_usage(), settings.public_host)
