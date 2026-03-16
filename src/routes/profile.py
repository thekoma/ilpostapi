from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from auth_dependencies import require_auth
from config import BASE_URL, SMTP_ENABLED, OIDC_ENABLED
from database import get_db
from database.user_operations import regenerate_rss_token

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="templates")


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user=Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    base_url = BASE_URL.rstrip("/")
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "base_url": base_url,
        "smtp_enabled": SMTP_ENABLED,
        "oidc_enabled": OIDC_ENABLED,
    })


@router.post("/profile/regenerate-token")
async def regenerate_token(
    request: Request,
    user=Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await regenerate_rss_token(db, user)
    return RedirectResponse("/profile", status_code=302)
