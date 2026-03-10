import asyncio
import base64
import json
import mimetypes
import os
from datetime import datetime, timezone
from functools import lru_cache
from html import escape
from pathlib import Path

# .env 파일 자동 로드 (python-dotenv 없어도 직접 파싱)
_env_file = Path(__file__).resolve().parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

_AUTO_SYNC_USERNAME: str = os.environ.get("MAJSOUL_USERNAME", "")
_AUTO_SYNC_PASSWORD: str = os.environ.get("MAJSOUL_PASSWORD", "")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from majsoul_client import fetch_summary

DATA_DIR = Path("data")
PLAYERS_DIR = DATA_DIR / "players"
NICKNAME_INDEX_FILE = DATA_DIR / "nickname_index.json"
RANK_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "ranks"
AVATAR_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "avatars"

RANK_ICON_FILES = {
    1: "Novice.png",
    2: "Intermediate.png",
    3: "Expert.png",
    4: "Master.png",
    5: "Saint.png",
    6: "Celestial.png",
}

RANK_ICON_FILES_3P = {
    1: "3pNovice.png",
    2: "3pIntermediate.png",
    3: "3pExpert.png",
    4: "3pMaster.png",
    5: "3pSaint.png",
    6: "3pCelestial.png",
}

# (tier, star) → (base_score, cap_score) based on in-game rank thresholds
_RANK_SCORE_RANGES: dict[tuple[int, int], tuple[int, int]] = {
    (1, 1): (0, 20),
    (1, 2): (0, 80),
    (1, 3): (0, 200),
    (2, 1): (300, 600),
    (2, 2): (400, 800),
    (2, 3): (500, 1000),
    (3, 1): (600, 1200),
    (3, 2): (700, 1400),
    (3, 3): (1000, 2000),
    (4, 1): (1400, 2800),
    (4, 2): (1600, 3200),
    (4, 3): (1800, 3600),
    (5, 1): (2000, 4000),
    (5, 2): (3000, 6000),
    (5, 3): (4500, 9000),
}

app = FastAPI(title="Majsoul Badge API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


async def _load_or_auto_sync(nickname: str) -> dict:
    """캐시된 데이터를 반환하고, 없으면 환경변수 계정으로 자동 sync 후 반환."""
    account_id = _find_account_id_by_nickname(nickname)
    if account_id is not None:
        file_path = _player_file(account_id)
        if file_path.exists():
            return json.loads(file_path.read_text(encoding="utf-8"))

    if not _AUTO_SYNC_USERNAME or not _AUTO_SYNC_PASSWORD:
        raise HTTPException(
            status_code=404,
            detail=(
                "Player data not found. "
                "Set MAJSOUL_USERNAME / MAJSOUL_PASSWORD in .env for auto-sync, "
                "or call POST /api/sync manually."
            ),
        )

    try:
        summary = await fetch_summary(
            username=_AUTO_SYNC_USERNAME,
            password=_AUTO_SYNC_PASSWORD,
            target_nickname=nickname,
            recent_count=10,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Auto-sync failed: {exc}")

    return _save_summary(summary, aliases=[nickname])


def _build_public_profile(payload: dict) -> dict:
    summary = payload.get("summary", {})
    account = summary.get("account", {})
    return {
        "nickname": account.get("nickname") or payload.get("nickname"),
        "account_id": account.get("account_id"),
        "avatar": account.get("avatar", {}),
        "updated_at": payload.get("updated_at"),
        "rank_4p": account.get("rank_4p", {}),
        "rank_3p": account.get("rank_3p", {}),
        "achievement_total": (account.get("achievement") or {}).get("total"),
        "recent_games": summary.get("recent_games", {}),
    }


@lru_cache(maxsize=50)
def _rank_icon_data_uri(tier: int) -> str:
    file_name = RANK_ICON_FILES.get(tier, "Expert.png")
    icon_path = RANK_ASSETS_DIR / file_name
    if not icon_path.exists():
        icon_path = RANK_ASSETS_DIR / "Expert.png"
    raw = icon_path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{encoded}"

@lru_cache(maxsize=16)
def _3rank_icon_data_uri(tier: int) -> str:
    file_name = RANK_ICON_FILES_3P.get(tier, "3pExpert.png")
    icon_path = RANK_ASSETS_DIR / file_name
    if not icon_path.exists():
        icon_path = RANK_ASSETS_DIR / "3pExpert.png"
    raw = icon_path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{encoded}"



@lru_cache(maxsize=256)
def _avatar_icon_data_uri(avatar_id: int) -> str:
    avatar_base = str(int(avatar_id))[:4] if avatar_id else "0"
    candidates = [
        AVATAR_ASSETS_DIR / f"{avatar_base}.svg",
        AVATAR_ASSETS_DIR / f"{avatar_base}.png",
        AVATAR_ASSETS_DIR / f"{avatar_base}.webp",
        AVATAR_ASSETS_DIR / f"{avatar_base}.jpg",
        AVATAR_ASSETS_DIR / f"{avatar_base}.jpeg",
        AVATAR_ASSETS_DIR / "default.svg",
    ]

    icon_path = next((p for p in candidates if p.exists()), AVATAR_ASSETS_DIR / "default.svg")
    raw = icon_path.read_bytes()
    mime_type = mimetypes.guess_type(str(icon_path))[0] or "image/svg+xml"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _build_badge_svg_mode(
    profile: dict,
    rank_key: str,
    recent_key: str,
    mode_label: str,
    max_rank: int,
    icon_data_uri: str,
) -> str:
    nickname = escape(str(profile.get("nickname") or "Unknown"))
    avatar = profile.get("avatar") or {}
    avatar_id = int(avatar.get("avatar_id") or 0)
    avatar_base = str(avatar_id)[:4] if avatar_id else "-"
    avatar_text = f"A#{avatar_base}" if avatar_id else "A#-"
    avatar_data_uri = _avatar_icon_data_uri(avatar_id)
    rank_data = profile.get(rank_key) or {}
    rank_text = escape(str(rank_data.get("name_ko") or f"ID {rank_data.get('id', '-')}"))
    score_text = escape(str(rank_data.get("score", "-")))
    subtitle1 = f"{mode_label} {rank_text}"
    subtitle2 = f"{score_text} pt" if score_text != "-" else ""

    tier_name = str(rank_data.get("name_ko") or "").split(" ")[0]
    tier = int(rank_data.get("tier") or 0)
    star = int(rank_data.get("star") or 0)

    

    _themes = {
        1: {  # 초심 Novice — 연두색
            "bg_start": "#4a7a20",
            "bg_end": "#a8d850",
            "panel": "rgba(210, 245, 180, 0.20)",
            "line_start": "#d8f890",
            "line_end": "#f0ffdc",
        },
        2: {  # 작사 Adept — 초록색
            "bg_start": "#1a6630",
            "bg_end": "#3aaa5a",
            "panel": "rgba(190, 240, 210, 0.20)",
            "line_start": "#80e8a8",
            "line_end": "#d0fce0",
        },
        3: {  # 작걸 Expert — 황금색
            "bg_start": "#a67a00",
            "bg_end": "#f5c842",
            "panel": "rgba(255, 243, 201, 0.22)",
            "line_start": "#ffe28a",
            "line_end": "#fff7d6",
        },
        4: {  # 작호 Master — 주황색
            "bg_start": "#a14a12",
            "bg_end": "#f08b3a",
            "panel": "rgba(255, 229, 204, 0.22)",
            "line_start": "#ffc28a",
            "line_end": "#ffe9d6",
        },
        5: {  # 작성 Saint — 장미/핑크
            "bg_start": "#7f2050",
            "bg_end": "#d96090",
            "panel": "rgba(255, 210, 230, 0.20)",
            "line_start": "#ffaad0",
            "line_end": "#ffe4ef",
        },
        6: {  # 작혼천 Celestial — 보라색
            "bg_start": "#3a2080",
            "bg_end": "#8860d0",
            "panel": "rgba(220, 200, 255, 0.20)",
            "line_start": "#c8a8ff",
            "line_end": "#ede0ff",
        },
    }
    theme = _themes.get(
        tier,
        {  # 기본 (알 수 없는 등급) — 초록
            "bg_start": "#1f7348",
            "bg_end": "#3b9c62",
            "panel": "rgba(255,255,255,0.16)",
            "line_start": "#fff1a8",
            "line_end": "#ffffff",
        },
    )

    if not tier_name:
        tier_name = "등급"

    visible_stars = min(max(star, 0), 5)
    star_text = "★" * visible_stars
    if star > 5:
        star_text += f"x{star}"

    # Gauge progress bar
    score_int = 0
    try:
        score_int = int(rank_data.get("score") or 0)
    except (ValueError, TypeError):
        pass

    score_range = _RANK_SCORE_RANGES.get((tier, star))
    gauge_svg = ""
    if score_range:
        base_score, cap_score = score_range
        span = cap_score
        progress = max(0.0, min(1.0, (score_int) / span)) if span > 0 else 1.0
        gx, gy, gw, gh = 226, 75, 85, 12
        fill_w = max(0.0, gw * progress)
        gauge_color = theme["line_start"]
        gauge_svg = (
            f"<rect x='{gx}' y='{gy}' width='{gw}' height='{gh}' rx='4' fill='rgba(255,255,255,0.22)'/>"
            f"<rect x='{gx}' y='{gy}' width='{fill_w:.1f}' height='{gh}' rx='4' fill='{gauge_color}' fill-opacity='0.85'/>"
            f"<text x='{gx + gw / 2 - 1}' y='{gy - 10}' text-anchor='middle' fill='rgba(234,255,242,0.88)' font-size='14' "
            f"font-family='Segoe UI, Malgun Gothic, sans-serif'>{score_int}/{cap_score} </text>"
        )

    recent_games = ((profile.get("recent_games") or {}).get(recent_key) or [])[:10]
    # recent list is latest-first in current payload; reverse so latest appears on the right side.
    recent_games = list(reversed(recent_games))
    ranks = []
    for item in recent_games:
        if not isinstance(item, dict):
            continue
        value = int(item.get("rank", max_rank))
        ranks.append(max(1, min(max_rank, value)))

    chart_x = 40
    chart_y = 120
    chart_w = 390
    chart_h = 58

    polyline = ""
    rank_grid_lines = ""
    rank_labels = ""
    point_dots = ""

    def y_from_rank(rank_value: int) -> float:
        # rank 1 should be top row.
        denominator = max(1, max_rank - 1)
        return chart_y + ((rank_value - 1) / denominator) * chart_h

    for rank_value in range(1, max_rank + 1):
        y = y_from_rank(rank_value)
        rank_grid_lines += (
            f"<line x1='{chart_x}' y1='{y:.1f}' x2='{chart_x + chart_w}' y2='{y:.1f}' "
            "stroke='rgba(255,255,255,0.38)' stroke-dasharray='4 4'/>"
        )
        rank_labels += (
            f"<text x='{chart_x - 10}' y='{y + 4:.1f}' fill='rgba(234,255,242,0.95)' "
            "font-size='11' text-anchor='end' font-family='Segoe UI, Malgun Gothic, sans-serif'>"
            f"{rank_value}등</text>"
        )

    if ranks:
        coords = []
        for idx, rank_value in enumerate(ranks):
            if len(ranks) == 1:
                x = chart_x + chart_w / 2
            else:
                x = chart_x + (chart_w * idx / (len(ranks) - 1))
            y = y_from_rank(rank_value)
            coords.append((x, y))

        polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        for x, y in coords:
            point_dots += f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3.6' fill='#fff6b0' stroke='#ffffff' stroke-width='1.2'/>"

    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='450' height='200' role='img' aria-label='Majsoul profile badge'>
  <defs>
    <linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
            <stop offset='0%' stop-color='{theme["bg_start"]}'/>
            <stop offset='100%' stop-color='{theme["bg_end"]}'/>
    </linearGradient>
        <linearGradient id='lineg' x1='0' y1='0' x2='1' y2='0'>
            <stop offset='0%' stop-color='{theme["line_start"]}'/>
            <stop offset='100%' stop-color='{theme["line_end"]}'/>
        </linearGradient>
  </defs>
    <rect width='450' height='200' rx='16' fill='url(#g)'/>
        <rect x='8' y='8' width='434' height='184' rx='12' fill='{theme["panel"]}'/>
    <rect x='16' y='16' width='72' height='72' rx='14' fill='rgba(255,255,255,0.20)' stroke='rgba(255,255,255,0.50)'/>
    <clipPath id='avatarClip'>
        <rect x='20' y='20' width='64' height='64' rx='12'/>
    </clipPath>
    <image x='20' y='20' width='64' height='64' href='{avatar_data_uri}' preserveAspectRatio='xMidYMid slice' clip-path='url(#avatarClip)'/>
    <text x='96' y='48' fill='#ffffff' font-size='28' font-family='Segoe UI, Malgun Gothic, sans-serif' font-weight='700'>{nickname}</text>
    <rect x='230' y='22' width='76' height='24' rx='12' fill='rgba(255,255,255,0.22)' stroke='rgba(255,255,255,0.48)'/>
    <text x='30' y='20' fill='#f8fff9' font-size='12' text-anchor='middle' font-family='Segoe UI, Malgun Gothic, sans-serif'>{escape(avatar_text)}</text>
    <text x='96' y='84' fill='#eafff2' font-size='20' font-family='Segoe UI, Malgun Gothic, sans-serif'>{escape(subtitle1)}</text>
    {gauge_svg}
    <rect x='337' y='15' width='94' height='94' rx='12' fill='rgba(255,255,255,0.18)' stroke='rgba(255,255,255,0.45)'/>
    <image x='340' y='17' width='90' height='90' href='{icon_data_uri}' preserveAspectRatio='xMidYMid meet'/>
    <text x='268' y='38' fill='#fff4c5' font-size='16' text-anchor='middle' font-family='Segoe UI, Malgun Gothic, sans-serif'>{escape(star_text or '-')}</text>
    <text x='24' y='110' fill='rgba(234,255,242,0.95)' font-size='15' font-family='Segoe UI, Malgun Gothic, sans-serif'>대국 기록</text>
    <rect x='{chart_x}' y='{chart_y}' width='{chart_w}' height='{chart_h}' rx='8' fill='rgba(255,255,255,0.14)'/>
    {rank_grid_lines}
    {rank_labels}
    <polyline points='{polyline}' fill='none' stroke='url(#lineg)' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/>
    {point_dots}
</svg>"""


def _build_badge_svg(profile: dict) -> str:
    return _build_badge_svg_mode(
        profile=profile,
        rank_key="rank_4p",
        recent_key="four_player",
        mode_label="4P",
        max_rank=4,
        icon_data_uri = _rank_icon_data_uri(int((profile.get("rank_4p") or {}).get("tier") or 0))
    )
    
def _build_badge3_svg(profile: dict) -> str:
    return _build_badge_svg_mode(
        profile=profile,
        rank_key="rank_3p",
        recent_key="three_player",
        mode_label="3P",
        max_rank=3,
        icon_data_uri = _3rank_icon_data_uri(int((profile.get("rank_3p") or {}).get("tier") or 0))
    )


@app.get("/api/player/{nickname}/badge.svg")
async def get_player_badge_svg(nickname: str):
    payload = await _load_or_auto_sync(nickname)
    profile = _build_public_profile(payload)
    svg = _build_badge_svg(profile)
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/api/player/{nickname}/badge3.svg")
async def get_player_badge3_svg(nickname: str):
    payload = await _load_or_auto_sync(nickname)
    profile = _build_public_profile(payload)
    svg = _build_badge3_svg(profile)
    return Response(content=svg, media_type="image/svg+xml")



# --- 짧은 alias URL (GitHub README 임베드용) ---

@app.get("/badge/{nickname}")
async def get_badge_short(nickname: str):
    payload = await _load_or_auto_sync(nickname)
    profile = _build_public_profile(payload)
    svg = _build_badge_svg(profile)
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/badge3/{nickname}")
async def get_badge3_short(nickname: str):
    payload = await _load_or_auto_sync(nickname)
    profile = _build_public_profile(payload)
    svg = _build_badge3_svg(profile)
    return Response(content=svg, media_type="image/svg+xml")
