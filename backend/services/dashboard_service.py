from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Conversation, InferenceLog, InferenceStatus
from pricing import cost_for
from schemas import DashboardStats, ModelUsage, ThroughputPoint

# Throughput window. Hourly buckets over a day is enough to see load shape
# without paging a lot of rows into the response.
THROUGHPUT_HOURS = 24


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

        # Throughput: count per hour bucket. date_trunc keeps the grouping in
        # the database, and created_at is indexed, so this stays cheap.
        since = datetime.now(timezone.utc) - timedelta(hours=THROUGHPUT_HOURS)
        bucket = func.date_trunc("hour", InferenceLog.created_at).label("bucket")
        throughput_stmt = (
            select(
                bucket,
                func.count(InferenceLog.id),
                func.sum(case((InferenceLog.status == InferenceStatus.FAILED, 1), else_=0)),
            )
            .join(Conversation, InferenceLog.conversation_id == Conversation.id)
            .where(Conversation.user_id == user_id, InferenceLog.created_at >= since)
            .group_by(bucket)
            .order_by(bucket)
        )
        throughput_rows = (await self.session.execute(throughput_stmt)).all()

        # Cost is derived here rather than stored on the row: prices change,
        # and a cost written at ingest time would silently freeze the old rate.
        models: list[ModelUsage] = []
        unpriced: list[str] = []
        total_cost = 0.0

        for model, calls, latency, p, c in model_rows:
            cost = cost_for(model, p or 0, c or 0)
            if cost is None:
                unpriced.append(model)
            else:
                total_cost += cost

            models.append(
                ModelUsage(
                    model=model,
                    calls=calls,
                    avg_latency_ms=int(latency or 0),
                    prompt_tokens=p or 0,
                    completion_tokens=c or 0,
                    cost_usd=cost,
                )
            )

        return DashboardStats(
            total_calls=total or 0,
            success_calls=success or 0,
            failed_calls=(total or 0) - (success or 0),
            avg_latency_ms=int(avg_latency or 0),
            total_prompt_tokens=prompt or 0,
            total_completion_tokens=completion or 0,
            total_tokens=total_tokens or 0,
            total_cost_usd=round(total_cost, 6),
            unpriced_models=unpriced,
            models=models,
            throughput=[
                ThroughputPoint(bucket=b, calls=calls, failed=failed or 0)
                for b, calls, failed in throughput_rows
            ],
        )
