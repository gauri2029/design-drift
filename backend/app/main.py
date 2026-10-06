from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

# Refuse to run outside local development with the checked-in token secret:
# it would mean anyone holding this repo could mint valid tokens. Failing at
# startup rather than logging a warning, because a warning would ship.
if settings.app_env != "local" and settings.jwt_secret_is_default:
    raise RuntimeError(
        "JWT_SECRET_KEY is still the development default. Set it to a random "
        "secret (e.g. `openssl rand -hex 32`) before running outside local."
    )

app = FastAPI(title="Design Drift API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)
