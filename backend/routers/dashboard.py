from fastapi import APIRouter

from schemas import DashboardStats
from security import CurrentUser, SessionDep
from services.dashboard_service import DashboardService

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@dashboard_router.get("", response_model=DashboardStats)
async def dashboard(user: CurrentUser, session: SessionDep) -> DashboardStats:
    """Inference stats across the whole deployment, not just the caller's own
    calls — this is the operator's view of the app.

    Still requires a signed-in user: the numbers are app-wide, but they aren't
    public. `user` is the authentication gate and nothing more, which is why it
    isn't passed to the service.
    """
    return await DashboardService(session).stats()
