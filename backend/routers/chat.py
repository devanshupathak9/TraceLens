
import json
import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from database import session_scope
from schemas import MessageCreate, MessageOut, SendMessageResponse
from security import CurrentUser, SessionDep
from services.chat_service import ChatService, ClientDisconnected, LLMCallFailed
from services.conversation_service import ConversationNotFound, ConversationService

logger = logging.getLogger("chatjippity")


def _sse(event: str, data: dict) -> str:
    """One SSE frame. The blank line terminates it — without it the client
    buffers forever waiting for more of the same event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

chat_router = APIRouter(
    prefix="/conversations",
    tags=["Messages"],
)


@chat_router.post("/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: int,
    payload: MessageCreate,
    user: CurrentUser,
    session: SessionDep,
    request: Request,
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
            conversation, payload.content, request
        )
    except ClientDisconnected:
        # The user hit stop; nobody is listening for this response. 499 is
        # nginx's "client closed request" code.
        raise HTTPException(499, "Client closed request")
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


@chat_router.post("/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: int,
    payload: MessageCreate,
    user: CurrentUser,
) -> StreamingResponse:
    """The same chat turn as POST /messages, streamed token by token over SSE.

    Deliberately does NOT use the request-scoped session dependency: the body of
    a StreamingResponse runs after the handler returns, so that session (and its
    pooled connection) would be held open for the whole generation. It opens its
    own via session_scope() instead, for the lifetime of the stream.
    """

    async def frames():
        async with session_scope() as session:
            try:
                conversation = await ConversationService(session).get(
                    conversation_id, user.id, with_messages=True
                )
            except ConversationNotFound:
                yield _sse("error", {"detail": "Conversation not found"})
                return

            try:
                async for kind, data in ChatService(session).stream_message(
                    conversation, payload.content
                ):
                    if kind == "delta":
                        yield _sse("delta", {"text": data})
                    else:
                        user_message, assistant_message = data
                        yield _sse(
                            "done",
                            {
                                "user_message": MessageOut.model_validate(
                                    user_message
                                ).model_dump(mode="json"),
                                "assistant_message": MessageOut.model_validate(
                                    assistant_message
                                ).model_dump(mode="json"),
                            },
                        )
            except LLMCallFailed:
                logger.exception("streamed LLM call failed")
                yield _sse(
                    "error",
                    {"detail": "The model provider request failed. Please try again."},
                )

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            # Stops nginx buffering the whole stream into one lump; without it
            # the client gets the reply all at once at the end.
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


@chat_router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: int, user: CurrentUser, session: SessionDep
) -> list[MessageOut]:
    """The conversation's transcript, oldest first."""
    try:
        messages = await ConversationService(session).list_messages(conversation_id, user.id)
    except ConversationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    return [MessageOut.model_validate(message) for message in messages]
