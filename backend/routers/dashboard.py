from fastapi import APIRouter

from schemas import DashboardStats
from security import CurrentUser, SessionDep
from services.dashboard_service import DashboardService

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@dashboard_router.get("", response_model=DashboardStats)
async def dashboard(user: CurrentUser, session: SessionDep) -> DashboardStats:
    """Inference stats for the signed-in user's conversations."""
    return await DashboardService(session).stats_for_user(user.id)
