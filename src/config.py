import os
import secrets

from dotenv import load_dotenv, find_dotenv
from utils.logging import setup_logging, get_logger

load_dotenv(find_dotenv())

setup_logging()
logger = get_logger(__name__)

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

if not EMAIL or not PASSWORD:
    logger.error("EMAIL and PASSWORD are required but not set properly")
    raise ValueError("EMAIL and PASSWORD are required but not set properly")

PODCAST_API_BASE_URL = "https://api-prod.ilpost.it/podcast/v1/podcast"
BFF_HP_URL = "https://api-prod.ilpost.it/podcast/v1/bff/hp"
API_AUTH_LOGIN = "https://api-prod.ilpost.it/user/v1/auth/login"
API_KEY = "testapikey"

TOKEN_CACHE_TTL = 2 * 60 * 60  # 2 hours
CACHE_TTL = 15 * 60  # 15 minutes

BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

# Session secret key
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))

# OIDC Configuration (Authentik)
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "")  # e.g. https://auth.example.com/application/o/ilpostapi/
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "")  # e.g. https://app.example.com/auth/callback
OIDC_ADMIN_GROUP = os.getenv("OIDC_ADMIN_GROUP", "admin")  # group name for admin role
OIDC_PROVIDER_NAME = os.getenv("OIDC_PROVIDER_NAME", "SSO")  # display name on login button
OIDC_ENABLED = bool(OIDC_ISSUER and OIDC_CLIENT_ID and OIDC_CLIENT_SECRET)

# SMTP Configuration (optional, for password reset emails)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
SMTP_ENABLED = bool(SMTP_HOST and SMTP_FROM)
