from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Conversation, InferenceLog, InferenceStatus
from schemas import DashboardStats, ModelUsage


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def stats_for_user(self, user_id: int) -> DashboardStats:
        # Logs belong to the user through their conversations.
        totals_stmt = (
            select(
                func.count(InferenceLog.id),
                func.sum(case((InferenceLog.status == InferenceStatus.SUCCESS, 1), else_=0)),
                func.avg(InferenceLog.latency_ms),
                func.sum(InferenceLog.prompt_tokens),
                func.sum(InferenceLog.completion_tokens),
                func.sum(InferenceLog.total_tokens),
            )
            .join(Conversation, InferenceLog.conversation_id == Conversation.id)
            .where(Conversation.user_id == user_id)
        )
        total, success, avg_latency, prompt, completion, total_tokens = (
            (await self.session.execute(totals_stmt)).one()
        )

        models_stmt = (
            select(
                InferenceLog.model,
                func.count(InferenceLog.id),
                func.avg(InferenceLog.latency_ms),
                func.sum(InferenceLog.prompt_tokens),
                func.sum(InferenceLog.completion_tokens),
            )
            .join(Conversation, InferenceLog.conversation_id == Conversation.id)
            .where(Conversation.user_id == user_id)
            .group_by(InferenceLog.model)
            .order_by(func.count(InferenceLog.id).desc())
        )
        model_rows = (await self.session.execute(models_stmt)).all()

        return DashboardStats(
            total_calls=total or 0,
            success_calls=success or 0,
            failed_calls=(total or 0) - (success or 0),
            avg_latency_ms=int(avg_latency or 0),
            total_prompt_tokens=prompt or 0,
            total_completion_tokens=completion or 0,
            total_tokens=total_tokens or 0,
            models=[
                ModelUsage(
                    model=model,
                    calls=calls,
                    avg_latency_ms=int(latency or 0),
                    prompt_tokens=p or 0,
                    completion_tokens=c or 0,
                )
                for model, calls, latency, p, c in model_rows
            ],
        )
