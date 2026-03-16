from datetime import datetime, timezone

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from auth_dependencies import require_auth
from config import (
    OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, OIDC_REDIRECT_URI,
    OIDC_ENABLED, OIDC_ADMIN_GROUP, OIDC_PROVIDER_NAME,
    SMTP_ENABLED, SECRET_KEY, BASE_URL,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_USE_TLS,
    logger,
)
from database import get_db
from database.user_operations import (
    get_user_count, get_user_by_username, get_user_by_email,
    get_user_by_oauth_sub, create_user, update_user_password,
    verify_password, update_user_oauth_sub,
)

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="templates")

# Setup OIDC
oauth = OAuth()
if OIDC_ENABLED:
    oauth.register(
        name="authentik",
        client_id=OIDC_CLIENT_ID,
        client_secret=OIDC_CLIENT_SECRET,
        server_metadata_url=f"{OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile groups"},
    )


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, db: AsyncSession = Depends(get_db)):
    """First-time setup: create the initial admin user."""
    user_count = await get_user_count(db)
    if user_count > 0:
        return RedirectResponse("/auth/login", status_code=302)

    return templates.TemplateResponse("auth/setup.html", {
        "request": request,
        "error": None,
    })


@router.post("/setup")
async def setup_create_admin(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Create the first admin user."""
    user_count = await get_user_count(db)
    if user_count > 0:
        return RedirectResponse("/auth/login", status_code=302)

    if password != password_confirm:
        return templates.TemplateResponse("auth/setup.html", {
            "request": request,
            "error": "Le password non corrispondono",
        })

    if len(password) < 8:
        return templates.TemplateResponse("auth/setup.html", {
            "request": request,
            "error": "La password deve essere di almeno 8 caratteri",
        })

    user = await create_user(db, username=username, email=email, password=password, role="admin")
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Login page."""
    user_count = await get_user_count(db)
    if user_count == 0:
        return RedirectResponse("/auth/setup", status_code=302)

    # Already logged in
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse("auth/login.html", {
        "request": request,
        "error": None,
        "oidc_enabled": OIDC_ENABLED,
        "oidc_provider_name": OIDC_PROVIDER_NAME,
        "smtp_enabled": SMTP_ENABLED,
    })


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle login form submission."""
    user = await get_user_by_username(db, username)
    if not user:
        user = await get_user_by_email(db, username)

    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Credenziali non valide",
            "oidc_enabled": OIDC_ENABLED,
            "oidc_provider_name": OIDC_PROVIDER_NAME,
            "smtp_enabled": SMTP_ENABLED,
        })

    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=302)


@router.get("/login/oidc")
async def login_oidc(request: Request):
    """Redirect to OIDC provider."""
    if not OIDC_ENABLED:
        raise HTTPException(status_code=404, detail="OIDC non configurato")
    redirect_uri = OIDC_REDIRECT_URI or str(request.url_for("oidc_callback"))
    return await oauth.authentik.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def oidc_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle OIDC callback from Authentik."""
    if not OIDC_ENABLED:
        raise HTTPException(status_code=404, detail="OIDC non configurato")

    try:
        token = await oauth.authentik.authorize_access_token(request)
    except Exception as e:
        logger.error(f"OIDC callback error: {e}")
        return RedirectResponse("/auth/login", status_code=302)

    userinfo = token.get("userinfo")
    # Also fetch from userinfo endpoint to get groups claim
    try:
        userinfo_response = await oauth.authentik.userinfo(token=token, request=request)
        if userinfo_response:
            logger.info(f"OIDC userinfo endpoint response: {dict(userinfo_response)}")
            # Merge: userinfo endpoint takes precedence (has groups)
            if userinfo:
                merged = dict(userinfo)
                merged.update(dict(userinfo_response))
                userinfo = merged
            else:
                userinfo = dict(userinfo_response)
    except Exception as e:
        logger.warning(f"OIDC userinfo endpoint call failed: {e}")

    if not userinfo:
        return RedirectResponse("/auth/login", status_code=302)

    sub = userinfo.get("sub")
    email = userinfo.get("email", "")
    preferred_username = userinfo.get("preferred_username", email.split("@")[0] if email else sub)
    groups = userinfo.get("groups", [])

    logger.info(f"OIDC userinfo: sub={sub}, email={email}, username={preferred_username}")
    logger.info(f"OIDC groups received: {groups}")
    logger.info(f"OIDC admin group configured: {OIDC_ADMIN_GROUP!r}")

    # Determine role from groups
    role = "admin" if OIDC_ADMIN_GROUP in groups else "user"
    logger.info(f"OIDC determined role: {role}")

    # Try to find existing user by oauth_sub
    user = await get_user_by_oauth_sub(db, sub)

    if not user:
        # Try to find by email and link
        user = await get_user_by_email(db, email)
        if user:
            await update_user_oauth_sub(db, user, sub)
            # Update role based on groups
            user.role = role
            await db.commit()
        else:
            # Create new user
            user = await create_user(
                db,
                username=preferred_username,
                email=email,
                role=role,
                oauth_sub=sub,
            )
    else:
        # Update role based on groups on every login
        user.role = role
        await db.commit()

    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    """Logout."""
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=302)


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(
    request: Request,
    user=Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    return templates.TemplateResponse("auth/change_password.html", {
        "request": request,
        "user": user,
        "error": None,
        "success": None,
        "smtp_enabled": SMTP_ENABLED,
    })


@router.post("/change-password")
async def change_password_submit(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    user=Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    if new_password != new_password_confirm:
        return templates.TemplateResponse("auth/change_password.html", {
            "request": request, "user": user,
            "error": "Le nuove password non corrispondono", "success": None,
            "smtp_enabled": SMTP_ENABLED,
        })

    if len(new_password) < 8:
        return templates.TemplateResponse("auth/change_password.html", {
            "request": request, "user": user,
            "error": "La nuova password deve essere di almeno 8 caratteri", "success": None,
            "smtp_enabled": SMTP_ENABLED,
        })

    if not user.password_hash or not verify_password(old_password, user.password_hash):
        return templates.TemplateResponse("auth/change_password.html", {
            "request": request, "user": user,
            "error": "La vecchia password non è corretta", "success": None,
            "smtp_enabled": SMTP_ENABLED,
        })

    await update_user_password(db, user, new_password)
    return templates.TemplateResponse("auth/change_password.html", {
        "request": request, "user": user,
        "error": None, "success": "Password aggiornata con successo",
        "smtp_enabled": SMTP_ENABLED,
    })


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    if not SMTP_ENABLED:
        raise HTTPException(status_code=404, detail="SMTP non configurato")
    return templates.TemplateResponse("auth/forgot_password.html", {
        "request": request,
        "error": None,
        "success": None,
    })


@router.post("/forgot-password")
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not SMTP_ENABLED:
        raise HTTPException(status_code=404, detail="SMTP non configurato")

    user = await get_user_by_email(db, email)
    # Always show success to prevent email enumeration
    if user:
        from itsdangerous import URLSafeTimedSerializer
        serializer = URLSafeTimedSerializer(SECRET_KEY)
        token = serializer.dumps(user.email, salt="password-reset")
        reset_url = f"{BASE_URL}/auth/reset-password/{token}"
        await _send_reset_email(user.email, reset_url)

    return templates.TemplateResponse("auth/forgot_password.html", {
        "request": request,
        "error": None,
        "success": "Se l'email esiste, riceverai un link per reimpostare la password",
    })


@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str):
    if not SMTP_ENABLED:
        raise HTTPException(status_code=404, detail="SMTP non configurato")

    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    try:
        serializer.loads(token, salt="password-reset", max_age=3600)
    except (SignatureExpired, BadSignature):
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request, "token": token,
            "error": "Link non valido o scaduto", "valid": False,
        })

    return templates.TemplateResponse("auth/reset_password.html", {
        "request": request, "token": token,
        "error": None, "valid": True,
    })


@router.post("/reset-password/{token}")
async def reset_password_submit(
    request: Request,
    token: str,
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not SMTP_ENABLED:
        raise HTTPException(status_code=404, detail="SMTP non configurato")

    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    try:
        email = serializer.loads(token, salt="password-reset", max_age=3600)
    except (SignatureExpired, BadSignature):
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request, "token": token,
            "error": "Link non valido o scaduto", "valid": False,
        })

    if new_password != new_password_confirm:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request, "token": token,
            "error": "Le password non corrispondono", "valid": True,
        })

    if len(new_password) < 8:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request, "token": token,
            "error": "La password deve essere di almeno 8 caratteri", "valid": True,
        })

    user = await get_user_by_email(db, email)
    if not user:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request, "token": token,
            "error": "Utente non trovato", "valid": False,
        })

    await update_user_password(db, user, new_password)
    return RedirectResponse("/auth/login", status_code=302)


async def _send_reset_email(to_email: str, reset_url: str):
    """Send password reset email via SMTP."""
    import aiosmtplib
    from email.message import EmailMessage

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
