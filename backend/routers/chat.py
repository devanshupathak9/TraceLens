from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from schemas import MessageCreate, MessageOut, SendMessageResponse
from security import CurrentUser, SessionDep
from services.chat_service import ChatService, LLMCallFailed
from services.conversation_service import ConversationNotFound, ConversationService

chat_router = APIRouter(
    prefix="/conversations",
    tags=["Messages"],
)


@chat_router.post("/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    user: CurrentUser,
    session: SessionDep,
) -> SendMessageResponse:
    """One chat turn: store the user message, get the LLM reply, return both."""
    try:
        conversation = await ConversationService(session).get(
            conversation_id, user.id, with_messages=True
        )
    except ConversationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    try:
        user_message, assistant_message = await ChatService(session).send_message(
            conversation, payload.content
        )
    except LLMCallFailed:
        # The user message and a failed inference_logs row were still stored.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The model provider request failed. Please try again.",
        )

    return SendMessageResponse(
        user_message=MessageOut.model_validate(user_message),
        assistant_message=MessageOut.model_validate(assistant_message),
    )


@chat_router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: UUID, user: CurrentUser, session: SessionDep
) -> list[MessageOut]:
    """The conversation's transcript, oldest first."""
    try:
        messages = await ConversationService(session).list_messages(conversation_id, user.id)
    except ConversationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    return [MessageOut.model_validate(message) for message in messages]
