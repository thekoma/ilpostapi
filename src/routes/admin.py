from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from auth_dependencies import require_admin
from config import SMTP_ENABLED, SECRET_KEY, BASE_URL, logger
from database import get_db
from database.user_operations import (
    get_all_users, create_user, delete_user, get_user_by_id,
    get_user_by_username, get_user_by_email, update_user_role,
)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")


async def _render_users(request, admin, db, error=None, success=None):
    users = await get_all_users(db)
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "user": admin,
        "users": users,
        "error": error,
        "success": success,
        "smtp_enabled": SMTP_ENABLED,
    })


@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _render_users(request, admin, db)


@router.post("/users/create")
async def create_user_route(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(""),
    role: str = Form("user"),
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    username = username.strip()
    email = email.strip()

    if role not in ("admin", "user"):
        role = "user"

    if await get_user_by_username(db, username):
        return await _render_users(request, admin, db,
                                   error=f"Username \"{username}\" gia in uso")

    if await get_user_by_email(db, email):
        return await _render_users(request, admin, db,
                                   error=f"Email \"{email}\" gia in uso")

    # Se la password e' vuota, crea utente senza password e invia invito
    if not password:
        if not SMTP_ENABLED:
            return await _render_users(request, admin, db,
                                       error="SMTP non configurato: impossibile inviare l'invito. Specifica una password.")

        await create_user(db, username=username, email=email, password=None, role=role)
        await _send_invite_email(email)
        return await _render_users(request, admin, db,
                                   success=f"Utente \"{username}\" creato. Invito inviato a {email}")

    if len(password) < 8:
        return await _render_users(request, admin, db,
                                   error="La password deve essere di almeno 8 caratteri")

    await create_user(db, username=username, email=email, password=password, role=role)
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/role")
async def change_user_role(
    request: Request,
    user_id: int,
    role: str = Form(...),
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if role not in ("admin", "user"):
        return await _render_users(request, admin, db, error="Ruolo non valido")

    target = await get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    # Non puoi cambiare il ruolo dell'admin principale
    if target.id == 1:
        return await _render_users(request, admin, db,
                                   error="Non puoi cambiare il ruolo dell'admin principale")

    await update_user_role(db, target, role)
    return await _render_users(request, admin, db,
                               success=f"Ruolo di \"{target.username}\" aggiornato a {role}")


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(
    request: Request,
    user_id: int,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not SMTP_ENABLED:
        return await _render_users(request, admin, db,
                                   error="SMTP non configurato: impossibile inviare email di reset")

    target = await get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    token = serializer.dumps(target.email, salt="password-reset")
    reset_url = f"{BASE_URL}/auth/reset-password/{token}"
    await _send_reset_email(target.email, reset_url)

    return await _render_users(request, admin, db,
                               success=f"Email di reset password inviata a {target.email}")


@router.post("/users/{user_id}/delete")
async def delete_user_route(
    request: Request,
    user_id: int,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        return await _render_users(request, admin, db,
                                   error="Non puoi cancellare te stesso")

    target = await get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    if target.id == 1:
        return await _render_users(request, admin, db,
                                   error="Non puoi cancellare l\u2019admin principale")

    await delete_user(db, user_id)
    return RedirectResponse("/admin/users", status_code=302)


async def _send_invite_email(to_email: str):
    """Invia email di invito con link per impostare la password."""
    import aiosmtplib
    from email.message import EmailMessage
    from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_USE_TLS

    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    token = serializer.dumps(to_email, salt="password-reset")
    reset_url = f"{BASE_URL}/auth/reset-password/{token}"

    msg = EmailMessage()
    msg["Subject"] = "Sei stato invitato - ilPost Podcasts"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(
        f"Sei stato invitato a usare ilPost Podcasts.\n\n"
        f"Clicca sul seguente link per impostare la tua password:\n\n"
        f"{reset_url}\n\n"
        f"Il link scade tra 1 ora.\n"
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER or None,
            password=SMTP_PASSWORD or None,
            use_tls=SMTP_USE_TLS,
        )
    except Exception as e:
        logger.error(f"Errore invio email di invito: {e}")


async def _send_reset_email(to_email: str, reset_url: str):
    """Invia email di reset password."""
    import aiosmtplib
    from email.message import EmailMessage
    from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_USE_TLS

    msg = EmailMessage()
    msg["Subject"] = "Reimposta la tua password - ilPost Podcasts"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(
        f"Clicca sul seguente link per reimpostare la tua password:\n\n"
        f"{reset_url}\n\n"
        f"Il link scade tra 1 ora.\n\n"
        f"Se non hai richiesto il reset della password, ignora questa email."
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER or None,
            password=SMTP_PASSWORD or None,
            use_tls=SMTP_USE_TLS,
        )
    except Exception as e:
        logger.error(f"Errore invio email di reset: {e}")
