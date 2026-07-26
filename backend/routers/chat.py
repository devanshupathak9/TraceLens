from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from schemas import MessageCreate, MessageOut, SendMessageResponse
from security import CurrentUser, SessionDep
from services.chat_service import ChatService
from services.conversation_service import ConversationNotFound, ConversationService

chat_router = APIRouter(
    prefix="/conversations",
    tags=["Chat"],
)


@chat_router.post("/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    user: CurrentUser,
    session: SessionDep,
) -> SendMessageResponse:
    """One chat turn: store the user message, get the LLM reply, return both.

    An LLM failure still returns 200 — the assistant message comes back with
    status "error" and the reason in `error`, and both rows are stored, so the
    transcript stays intact.
    """
    try:
        conversation = await ConversationService(session).get(
            conversation_id, user.id, with_messages=True
        )
    except ConversationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    user_message, assistant_message = await ChatService(session).send_message(
        conversation, payload.content
    )

    return SendMessageResponse(
        user_message=MessageOut.model_validate(user_message),
        assistant_message=MessageOut.model_validate(assistant_message),
    )
