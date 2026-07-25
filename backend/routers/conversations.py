from fastapi import APIRouter, HTTPException
from services.conversation_service import ConverstationService

converstation_router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


@converstation_router.post("/")
async def create_conversation():
    pass


@converstation_router.get("/")
async def list_conversations():
    pass


@converstation_router.get("/{conversation_id}")
async def get_conversation(conversation_id: str):
    pass


@converstation_router.put("/{conversation_id}")
async def update_conversation(conversation_id: str):
    pass


@converstation_router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    pass