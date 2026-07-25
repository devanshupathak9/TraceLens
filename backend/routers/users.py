from fastapi import APIRouter, HTTPException
from services.user_service import UserService

user_router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@user_router.post("/register")
async def register():
    pass


@user_router.post("/login")
async def register():
    pass


@user_router.post("/logout")
async def register():
    pass