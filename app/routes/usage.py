from fastapi import APIRouter, Depends, HTTPException
from ..database import db
from ..deps import get_current_user   # import the user dependency
from datetime import date, timedelta

router = APIRouter(prefix="/usage", tags=["usage"])

PLANS = {0: 10, 1: 20, 2: 30}


@router.get("/dashboard")
async def get_dashboard(user=Depends(get_current_user)):
    """
    Dashboard showing API usage stats for the authenticated user.
    """
    usage = await db.usage.find_one({"user_id": user["_id"]})
    if not usage:
        # Create if missing
        usage = {
            "user_id": user["_id"],
            "calls_made_month": 0,
            "calls_today": 0,
            "last_reset": date.today().isoformat(),
        }
        await db.usage.insert_one(usage)

    # Get plan info
    plan = user.get("plan", 0)
    plan_limit = PLANS.get(plan, 10)

    # Last 7 days trend (group by date)
    today = date.today()
    start_date = today - timedelta(days=6)
    pipeline = [
        {"$match": {"user_id": user["_id"]}},
        {
            "$project": {
                "day": {"$substr": ["$last_reset", 0, 10]},
                "calls_today": 1,
            }
        },
        {
            "$group": {
                "_id": "$day",
                "calls": {"$max": "$calls_today"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    daily_stats = await db.usage.aggregate(pipeline).to_list(length=7)

    return {
        "username": user["username"],
        "plan": plan,
        "plan_limit": plan_limit,
        "calls_today": usage.get("calls_today", 0),
        "calls_made_month": usage.get("calls_made_month", 0),
        "daily_trend": daily_stats,
    }
