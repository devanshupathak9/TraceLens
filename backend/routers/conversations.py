from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    ConversationUpdate,
)
from security import CurrentUser, SessionDep
from services.conversation_service import ConversationNotFound, ConversationService

converstation_router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)

# Paths use "" rather than "/" so /api/v1/conversations matches without a redirect.


@converstation_router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate, user: CurrentUser, session: SessionDep
) -> ConversationSummary:
    conversation = await ConversationService(session).create(
        user.id, title=payload.title, model=payload.model
    )
    return ConversationSummary.model_validate(conversation)


@converstation_router.get("", response_model=list[ConversationSummary])
async def list_conversations(user: CurrentUser, session: SessionDep) -> list[ConversationSummary]:
    rows = await ConversationService(session).list_for_user(user.id)
    summaries = []
    for conversation, message_count in rows:
        summary = ConversationSummary.model_validate(conversation)
        summary.message_count = message_count
        summaries.append(summary)
    return summaries


@converstation_router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID, user: CurrentUser, session: SessionDep
) -> ConversationDetail:
    try:
        conversation = await ConversationService(session).get(
            conversation_id, user.id, with_messages=True
        )
    except ConversationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    detail = ConversationDetail.model_validate(conversation)
    detail.message_count = len(conversation.messages)
    return detail


@converstation_router.patch("/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> ConversationSummary:
    service = ConversationService(session)
    try:
        conversation = await service.update(conversation_id, user.id, title=payload.title)
    except ConversationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    summary = ConversationSummary.model_validate(conversation)
    summary.message_count = await service.count_messages(conversation_id)
    return summary


@converstation_router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID, user: CurrentUser, session: SessionDep
) -> None:
    try:
        await ConversationService(session).delete(conversation_id, user.id)
    except ConversationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
