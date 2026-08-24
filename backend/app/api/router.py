from fastapi import APIRouter

from app.api.routes import accounts, health, jobs, me

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(jobs.router)
api_router.include_router(accounts.router)
api_router.include_router(accounts.sessions_router)
api_router.include_router(me.router)
