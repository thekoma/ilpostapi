from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from auth_dependencies import require_admin
from database import get_db
from database.user_operations import (
    get_all_users, create_user, delete_user, get_user_by_id,
    get_user_by_username, get_user_by_email,
)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")


@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    users = await get_all_users(db)
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "user": admin,
        "users": users,
        "error": None,
        "success": None,
    })


@router.post("/users/create")
async def create_user_route(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    users = await get_all_users(db)

    if role not in ("admin", "user"):
        role = "user"

    if await get_user_by_username(db, username):
        return templates.TemplateResponse("admin/users.html", {
            "request": request, "user": admin, "users": users,
            "error": f"Username \"{username}\" gia in uso", "success": None,
        })

    if await get_user_by_email(db, email):
        return templates.TemplateResponse("admin/users.html", {
            "request": request, "user": admin, "users": users,
            "error": f"Email \"{email}\" gia in uso", "success": None,
        })

    if len(password) < 8:
        return templates.TemplateResponse("admin/users.html", {
            "request": request, "user": admin, "users": users,
            "error": "La password deve essere di almeno 8 caratteri", "success": None,
        })

    await create_user(db, username=username, email=email, password=password, role=role)
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/delete")
async def delete_user_route(
    request: Request,
    user_id: int,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Cannot delete yourself
    if user_id == admin.id:
        users = await get_all_users(db)
        return templates.TemplateResponse("admin/users.html", {
            "request": request, "user": admin, "users": users,
            "error": "Non puoi cancellare te stesso", "success": None,
        })

    # Cannot delete user with id=1 (first admin ever)
    target = await get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    if target.id == 1:
        users = await get_all_users(db)
        return templates.TemplateResponse("admin/users.html", {
            "request": request, "user": admin, "users": users,
            "error": "Non puoi cancellare l\u2019admin principale", "success": None,
        })

    await delete_user(db, user_id)
    return RedirectResponse("/admin/users", status_code=302)
