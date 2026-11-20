from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

# Startup checks, not warnings. Each of these is a misconfiguration that is
# invisible at runtime but means the deployment is unsafe, and a warning in
# a log nobody reads would ship.
if settings.app_env != "local":
    if settings.jwt_secret_is_default:
        raise RuntimeError(
            "JWT_SECRET_KEY is still the development default. Set it to a random "
            "secret (e.g. `openssl rand -hex 32`) before running outside local."
        )

    # A wildcard origin plus allow_credentials lets any site on the web make
    # credentialed calls to this API. Browsers reject that combination
    # anyway, so "*" here is not a working permissive setting — it is a
    # broken one that presents as unexplained CORS failures.
    if "*" in settings.cors_origin_list:
        raise RuntimeError(
            "CORS_ORIGINS must list the frontend's real origins outside local; "
            '"*" cannot be combined with credentialed requests.'
        )
    if not settings.cors_origin_list:
        raise RuntimeError(
            "CORS_ORIGINS is empty, so the frontend would be unable to call this API. "
            "Set it to the deployed frontend's origin, e.g. https://your-app.vercel.app"
        )

app = FastAPI(
    title="Design Drift API",
    version="0.1.0",
    description=(
        "Design QA agents that compare a Figma frame against a live page, "
        "trace findings to source, and propose patches a human approves."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    # Only the methods and headers the frontend actually sends. The previous
    # "*" was fine behind a localhost-only origin list; on a public API it
    # is a larger surface than anything here needs.
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_v1_router)
