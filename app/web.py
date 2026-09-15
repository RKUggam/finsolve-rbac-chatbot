"""Server-rendered web UI routes (login + chat), served by FastAPI via Jinja2."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["web"])


@router.get("/", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    """Login page. The client-side script redirects to /chat once authenticated."""
    return templates.TemplateResponse(request, "login.html")


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    """Chat page. Auth is enforced client-side (calls /auth/me) and server-side
    on every /api/chat call, so the page shell itself is safe to serve."""
    return templates.TemplateResponse(request, "chat.html")
