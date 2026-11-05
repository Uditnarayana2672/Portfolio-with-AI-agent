"""Aggregates all v1 feature routers under a single APIRouter.

`app/main.py` mounts this at the `/api/v1` prefix. Add each new feature's
router here (e.g. media, projects, blog) as it is built.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    activity,
    admin_inbox,
    blog_taxonomy,
    blogs,
    forms,
    internal_blogs,
    media,
    portfolio_content,
    projects,
    public_projects,
    public_site,
    users,
)

api_router = APIRouter()

api_router.include_router(users.router, tags=["users"])
api_router.include_router(media.router)
api_router.include_router(projects.router)
api_router.include_router(public_site.router)
api_router.include_router(public_projects.router)
api_router.include_router(forms.router)
api_router.include_router(blogs.router)
api_router.include_router(blog_taxonomy.router)
api_router.include_router(internal_blogs.router)
api_router.include_router(activity.router)
api_router.include_router(portfolio_content.router)
api_router.include_router(admin_inbox.router)
api_router.include_router(admin_inbox.internal_router)
