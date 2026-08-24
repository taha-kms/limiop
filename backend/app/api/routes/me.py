"""The signed-in account. Also the smallest possible proof the session works."""

from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.modules.accounts.schemas import AccountRead

router = APIRouter(prefix="/api/v1/me", tags=["accounts"])


@router.get("")
async def read_me(user: CurrentUser) -> AccountRead:
    return AccountRead.model_validate(user)
