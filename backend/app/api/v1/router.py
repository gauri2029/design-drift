from fastapi import APIRouter

from app.api.v1 import health, projects, reviews, scans

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router)
api_v1_router.include_router(projects.router)
api_v1_router.include_router(scans.router)
api_v1_router.include_router(reviews.router)
