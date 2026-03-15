import os
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
