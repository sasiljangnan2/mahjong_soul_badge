import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from majsoul_client import fetch_summary

DATA_DIR = Path("data")
PLAYERS_DIR = DATA_DIR / "players"
NICKNAME_INDEX_FILE = DATA_DIR / "nickname_index.json"
WEB_DIR = Path(__file__).resolve().parent / "web"

app = FastAPI(title="Majsoul Stats Sync API", version="0.1.0")


class SyncRequest(BaseModel):
    username: str = Field(..., description="Majsoul CN login account")
    password: str = Field(..., description="Majsoul CN login password")
    target_nickname: str | None = Field(default=None, description="Target nickname")
    secondary_nickname: str | None = Field(default=None, description="Alias nickname used for player load")
    recent_count: int = Field(default=10, ge=1, le=30, description="Recent records count per mode")


def _player_file(account_id: int) -> Path:
    return PLAYERS_DIR / f"{account_id}.json"


def _load_nickname_index() -> dict[str, int]:
    if not NICKNAME_INDEX_FILE.exists():
        return {}

    raw = json.loads(NICKNAME_INDEX_FILE.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in raw.items()}


def _save_nickname_index(index: dict[str, int]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NICKNAME_INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_account_id_by_nickname(nickname: str) -> int | None:
    index = _load_nickname_index()
    if nickname in index:
        return index[nickname]

    # Fallback scan for data files created before nickname index existed.
    for file_path in PLAYERS_DIR.glob("*.json"):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if payload.get("nickname") == nickname:
            account_id = int(payload["account_id"])
            index[nickname] = account_id
            _save_nickname_index(index)
            return account_id

    return None


def _save_summary(summary: dict, aliases: list[str] | None = None) -> dict:
    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
    account_id = summary["account"]["account_id"]
    nickname = summary["account"].get("nickname")
    payload = {
        "account_id": account_id,
        "nickname": nickname,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    }
    _player_file(account_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if nickname:
        index = _load_nickname_index()
        index[nickname] = int(account_id)
        for alias in aliases or []:
            cleaned = (alias or "").strip()
            if cleaned:
                index[cleaned] = int(account_id)
        _save_nickname_index(index)

    return payload


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/")
async def index():
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="web/index.html not found")
    return FileResponse(index_file)


@app.post("/api/sync")
async def sync_player(request: SyncRequest):
    try:
        summary = await fetch_summary(
            username=request.username,
            password=request.password,
            target_nickname=request.target_nickname,
            recent_count=request.recent_count,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    aliases = [request.target_nickname or "", request.secondary_nickname or ""]
    stored = _save_summary(summary, aliases=aliases)
    return {
        "ok": True,
        "nickname": stored.get("nickname"),
        "secondary_nickname": (request.secondary_nickname or "").strip() or None,
        "updated_at": stored["updated_at"],
    }


@app.get("/api/player/{nickname}")
async def get_player(nickname: str):
    account_id = _find_account_id_by_nickname(nickname)
    if account_id is None:
        raise HTTPException(status_code=404, detail="Player data not found. Call /api/sync with target_nickname first.")

    file_path = _player_file(account_id)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Player data file missing. Call /api/sync again.")

    return json.loads(file_path.read_text(encoding="utf-8"))
