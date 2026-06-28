import asyncio
import json
import os
import time as _time

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.models import create_db_and_tables, Settings, User, engine
from app.auth import (
    hash_password,
    verify_password,
    create_session_token,
    get_current_user,
    create_default_user,
    SESSION_COOKIE,
)
from app.ai import analyze_recipe
from app.tandoor import push_recipe_to_tandoor

app = FastAPI(title="Tandoor Recipe Importer")
templates = Jinja2Templates(directory="app/templates")

# ── Rate limiting state ───────────────────────────────────────────────────────
_analyze_lock = asyncio.Lock()
_analyze_in_progress = False
_last_analyze_done: float = 0.0
_ANALYZE_COOLDOWN = 10.0  # seconds between completed calls


@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    create_default_user()
    with Session(engine) as session:
        if not session.exec(select(Settings)).first():
            session.add(Settings())
            session.commit()


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/", 302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Ungültige Anmeldedaten"},
            status_code=401,
        )
    token = create_session_token(username)
    response = RedirectResponse("/", 302)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=86400)
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", 302)
    response.delete_cookie(SESSION_COOKIE)
    return response


# ── Settings ──────────────────────────────────────────────────────────────────
@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    if not get_current_user(request):
        return RedirectResponse("/login", 302)
    with Session(engine) as session:
        settings = session.exec(select(Settings)).first()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "settings": settings, "success": False, "error": None,
         "pw_success": False, "pw_error": None},
    )


@app.post("/settings", response_class=HTMLResponse)
def settings_post(
    request: Request,
    tandoor_url: str = Form(""),
    tandoor_api_key: str = Form(""),
    ai_provider: str = Form("openai"),
    ai_api_key: str = Form(""),
    ai_model: str = Form(""),
    ollama_base_url: str = Form("http://localhost:11434"),
):
    if not get_current_user(request):
        return RedirectResponse("/login", 302)
    with Session(engine) as session:
        s = session.exec(select(Settings)).first()
        s.tandoor_url = tandoor_url
        s.tandoor_api_key = tandoor_api_key
        s.ai_provider = ai_provider
        s.ai_api_key = ai_api_key
        s.ai_model = ai_model
        s.ollama_base_url = ollama_base_url
        session.add(s)
        session.commit()
        session.refresh(s)
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "settings": s, "success": True, "error": None,
         "pw_success": False, "pw_error": None},
    )


@app.post("/change-password", response_class=HTMLResponse)
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    username = get_current_user(request)
    if not username:
        return RedirectResponse("/login", 302)

    with Session(engine) as session:
        settings = session.exec(select(Settings)).first()
        user = session.exec(select(User).where(User.username == username)).first()

        if not verify_password(current_password, user.hashed_password):
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "settings": settings, "success": False, "error": None,
                 "pw_success": False, "pw_error": "Aktuelles Passwort ist falsch."},
            )
        if new_password != confirm_password:
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "settings": settings, "success": False, "error": None,
                 "pw_success": False, "pw_error": "Neues Passwort und Bestätigung stimmen nicht überein."},
            )
        if len(new_password) < 8:
            return templates.TemplateResponse(
                "settings.html",
                {"request": request, "settings": settings, "success": False, "error": None,
                 "pw_success": False, "pw_error": "Das neue Passwort muss mindestens 8 Zeichen lang sein."},
            )
        user.hashed_password = hash_password(new_password)
        session.add(user)
        session.commit()

    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "settings": settings, "success": False, "error": None,
         "pw_success": True, "pw_error": None},
    )


# ── Main / Index ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if not get_current_user(request):
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse("index.html", {"request": request})


# ── HTMX: Analyze ─────────────────────────────────────────────────────────────
@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, recipe_text: str = Form(...)):
    global _analyze_in_progress, _last_analyze_done

    if not get_current_user(request):
        return HTMLResponse('<div class="alert alert-danger">Nicht angemeldet</div>', 401)

    async with _analyze_lock:
        if _analyze_in_progress:
            return HTMLResponse(
                '<div class="alert alert-warning">Es läuft bereits eine Analyse. Bitte warten.</div>'
            )
        elapsed = _time.monotonic() - _last_analyze_done
        if _last_analyze_done > 0 and elapsed < _ANALYZE_COOLDOWN:
            remaining = int(_ANALYZE_COOLDOWN - elapsed) + 1
            return HTMLResponse(
                f'<div class="alert alert-warning">Bitte warte noch {remaining} Sekunden vor der nächsten Analyse.</div>'
            )
        _analyze_in_progress = True

    try:
        with Session(engine) as session:
            settings = session.exec(select(Settings)).first()

        recipe_json = await analyze_recipe(recipe_text, settings)
        raw_json = json.dumps(recipe_json, ensure_ascii=False, indent=2)
        return templates.TemplateResponse(
            "_recipe_preview.html",
            {
                "request": request,
                "recipe": recipe_json,
                "raw_json": raw_json,
                "recipe_text": recipe_text,
            },
        )
    except json.JSONDecodeError as e:
        return HTMLResponse(f'<div class="alert alert-danger">JSON-Parse-Fehler: {e}</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="alert alert-danger">KI-Fehler: {e}</div>')
    finally:
        async with _analyze_lock:
            _analyze_in_progress = False
            _last_analyze_done = _time.monotonic()


# ── HTMX: Transfer to Tandoor ─────────────────────────────────────────────────
@app.post("/transfer", response_class=HTMLResponse)
async def transfer(request: Request, recipe_json: str = Form(...)):
    if not get_current_user(request):
        return HTMLResponse('<div class="alert alert-danger">Nicht angemeldet</div>', 401)
    with Session(engine) as session:
        settings = session.exec(select(Settings)).first()
    try:
        data = json.loads(recipe_json)
        result = await push_recipe_to_tandoor(data, settings)
        if result["status_code"] == 201:
            recipe_url = f"{settings.tandoor_url.rstrip('/')}/recipe/{result['recipe_id']}/view/"
            return templates.TemplateResponse(
                "_transfer_success.html",
                {"request": request, "recipe_url": recipe_url},
            )
        return HTMLResponse(
            f'<div class="alert alert-danger">Fehler {result["status_code"]}: '
            f'<pre class="mt-2">{result["body"]}</pre></div>'
        )
    except json.JSONDecodeError as e:
        return HTMLResponse(f'<div class="alert alert-danger">JSON-Fehler: {e}</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="alert alert-danger">Übertragungsfehler: {e}</div>')
