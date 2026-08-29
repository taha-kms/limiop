from fastapi import APIRouter

from app.api.routes import accounts, analytics, cvs, health, jobs, matches, me, profile

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(jobs.router)
api_router.include_router(accounts.router)
api_router.include_router(accounts.sessions_router)
api_router.include_router(me.router)
api_router.include_router(cvs.router)
api_router.include_router(profile.router)
api_router.include_router(matches.router)
api_router.include_router(analytics.router)
