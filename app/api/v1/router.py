"""Aggregates all v1 feature routers under a single APIRouter.

`app/main.py` mounts this at the `/api/v1` prefix. Add each new feature's
router here (e.g. media, projects, blog) as it is built.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import media, projects, users

api_router = APIRouter()

api_router.include_router(users.router, tags=["users"])
api_router.include_router(media.router)
api_router.include_router(projects.router)
