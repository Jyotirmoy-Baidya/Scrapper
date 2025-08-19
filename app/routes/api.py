from fastapi import APIRouter, Header, HTTPException, Query
from ..database import db
from datetime import date, datetime
from bson import ObjectId
from ..utils.scraper import scrape_multiple_pages, format_json_output, format_text_output,format_markdown_output

router = APIRouter(prefix="/api", tags=["api"])

PLANS = {0: 10, 1: 20, 2: 30}

async def _reset_usage_if_needed(usage_doc):
    """
    usage_doc is from db. Should be a dict with keys:
    - calls_made_month (int)
    - calls_today (int)
    - last_reset (ISO date string like '2025-08-19')
    """
    today = date.today()
    last_reset_str = usage_doc.get("last_reset")
    try:
        last_reset = datetime.fromisoformat(last_reset_str).date()
    except Exception:
        last_reset = today

    updated = False

    # If month changed -> reset monthly counters
    if last_reset.month != today.month or last_reset.year != today.year:
        usage_doc["calls_made_month"] = 0
        usage_doc["calls_today"] = 0
        usage_doc["last_reset"] = today.isoformat()
        updated = True
    else:
        # same month but check daily reset
        if last_reset != today:
            usage_doc["calls_today"] = 0
            usage_doc["last_reset"] = today.isoformat()
            updated = True

    return usage_doc, updated

@router.get("/scrapper")
async def use_api(
    x_api_key: str = Header(None),
    url: str = Query(..., min_length=1, description="Target URL to scrape"),
    type: str = Query(..., min_length=1, description="Type/category of scraping"),
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="x-api-key header required")

    user = await db.users.find_one({"secret_token": x_api_key})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # fetch usage doc
    usage = await db.usage.find_one({"user_id": user["_id"]})
    if not usage:
        usage = {
            "user_id": user["_id"],
            "calls_made_month": 0,
            "calls_today": 0,
            "last_reset": date.today().isoformat()
        }
        await db.usage.insert_one(usage)

    # reset checks
    usage, changed = await _reset_usage_if_needed(usage)
    if changed:
        if usage.get("_id"):
            await db.usage.update_one({"_id": usage["_id"]}, {"$set": usage})
        else:
            await db.usage.update_one({"user_id": user["_id"]}, {"$set": usage})

    plan = user.get("plan", 0)
    plan_limit = PLANS.get(plan, 10)

    if usage["calls_made_month"] >= plan_limit:
        raise HTTPException(status_code=403, detail="Monthly API limit exceeded for your plan")

    # increment counters
    new_calls_made = usage["calls_made_month"] + 1
    new_calls_today = usage["calls_today"] + 1
    await db.usage.update_one(
        {"user_id": user["_id"]},
        {
            "$set": {
                "calls_made_month": new_calls_made,
                "calls_today": new_calls_today,
                "last_reset": usage["last_reset"],
            }
        },
    )

     # 🔥 Call the scraper here
    results = scrape_multiple_pages(url, max_pages=3)

    return {
        "message": "API call successful",
        "url": url,
        "type": type,
        "calls_today": new_calls_today,
        "calls_made_month": new_calls_made,
        "plan_limit": plan_limit,
        "result1": format_json_output(format_markdown_output(results)),
        "result2": format_text_output(results),
        "result3": format_markdown_output(results)
        # "scraped_data": scraped_data,
    }