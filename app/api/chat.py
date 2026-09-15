"""Chat API: the authenticated question-answering endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.rag.pipeline import answer_query
from app.rag.schemas import ChatResult
from app.rbac.policy import allowed_department_values

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(ChatResult):
    """Chat result plus context echoed back to the UI."""

    role: str
    accessible_departments: list[str]


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """Answer a question, scoped to the caller's role via RBAC."""
    result = answer_query(payload.message, current_user.role, username=current_user.username)
    return ChatResponse(
        **result.model_dump(),
        role=current_user.role.value,
        accessible_departments=allowed_department_values(current_user.role),
    )
