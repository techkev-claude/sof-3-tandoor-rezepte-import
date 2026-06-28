import httpx
from app.models import Settings


async def push_recipe_to_tandoor(recipe_data: dict, settings: Settings) -> dict:
    url = settings.tandoor_url.rstrip("/") + "/api/recipe/"
    headers = {
        "Authorization": f"Bearer {settings.tandoor_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=recipe_data, headers=headers)
    return {
        "status_code": response.status_code,
        "body": response.text,
        "recipe_id": response.json().get("id") if response.status_code == 201 else None,
    }
