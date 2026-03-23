import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import os   
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import formatdate
from functools import lru_cache
from html import escape
from pathlib import Path

logger = logging.getLogger("majsoul_badge")

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

from fastapi import FastAPI, HTTPException, Query, Request
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

SYNC_INTERVAL_SECONDS = int(os.environ.get("SYNC_INTERVAL", 86400))  # 기본 24시간


async def _background_sync_all() -> None:
    """알려진 모든 플레이어를 SYNC_INTERVAL_SECONDS 마다 재동기화한다."""
    if not _AUTO_SYNC_USERNAME or not _AUTO_SYNC_PASSWORD:
        logger.warning("[scheduler] MAJSOUL_USERNAME/PASSWORD 미설정 — 자동 sync 비활성화")
        return

    logger.warning("[scheduler] 백그라운드 sync 루프 시작 (간격: %ds)", SYNC_INTERVAL_SECONDS)
    while True:
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
        index = _load_nickname_index()
        nicknames = list(index.keys())
        if not index:
            logger.warning("[scheduler] 동기화할 플레이어 없음")
            continue
        logger.warning("[scheduler] %d명 sync 시작", len(index))
        seen = set()
        for nickname in nicknames:
            account_id = str(index.get(nickname))
            if account_id in seen:
                continue
            seen.add(account_id)
            try:
                summary = await fetch_summary(
                    username=_AUTO_SYNC_USERNAME,
                    password=_AUTO_SYNC_PASSWORD,
                    target_nickname=nickname,
                    recent_count=10,
                )
                _save_summary(summary, aliases=[nickname])
                logger.warning("[scheduler] ✓ %s", nickname)
            except Exception as exc:
                logger.warning("[scheduler] ✗ %s: %s", nickname, exc)
            # 계정 간 짧은 딜레이 (서버 부하 방지)
            await asyncio.sleep(2)
        logger.warning("[scheduler] 전체 sync 완료")


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(_background_sync_all())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Majsoul Badge API", version="0.1.0", lifespan=lifespan)

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

def _load_UID_index() -> dict[str, int]:
    if not NICKNAME_INDEX_FILE.exists():
        return {}

    raw = json.loads(NICKNAME_INDEX_FILE.read_text(encoding="utf-8"))
    return {int(k): int(v) for k, v in raw.items()}



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
    
    # 데이터 형식 정규화: recent_games를 새로운 형식으로 통일
    recent_games_raw = summary.get("recent_games", {})
    recent_games_normalized = {}
    for key in ["four_player", "three_player", "unknown"]:
        if key not in recent_games_raw:
            recent_games_normalized[key] = {"recent_games": [], "highest_hu": None}
        elif isinstance(recent_games_raw[key], list):
            # 이전 형식: 직접 list → 새 형식으로 변환
            recent_games_normalized[key] = {
                "recent_games": recent_games_raw[key],
                "highest_hu": None,
            }
        else:
            # 새로운 형식: 그대로 사용
            recent_games_normalized[key] = recent_games_raw[key]
    
    # 정규화된 데이터로 summary 업데이트
    summary_normalized = {**summary, "recent_games": recent_games_normalized}
    
    payload = {
        "account_id": account_id,
        "nickname": nickname,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary_normalized,
    }
    _player_file(account_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if nickname:
        index = _load_nickname_index()
        for alias in aliases or []:
            cleaned = (alias or "").strip()
            if cleaned:
                index[cleaned] = int(account_id)
        _save_nickname_index(index)
    return payload


async def _load_or_auto_sync(nickname: str, force: bool = True) -> dict:
    """캐시된 데이터를 반환하고, 없으면 환경변수 계정으로 자동 sync 후 반환.
    force=True이면 캐시를 무시하고 항상 새로 sync한다."""
    if not force:
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
    """저장된 데이터를 프로필 형식으로 변환 (이전/새로운 형식 모두 지원)"""
    summary = payload.get("summary", {})
    account = summary.get("account", {})
    recent_games_raw = summary.get("recent_games", {})
    
    # 데이터 형식 정규화: 이전 형식(직접 list)을 새 형식(dict with recent_games/highest_hu)으로 변환
    recent_games_normalized = {}
    for key in ["four_player", "three_player", "unknown"]:
        if key not in recent_games_raw:
            recent_games_normalized[key] = {"recent_games": [], "highest_hu": None}
        elif isinstance(recent_games_raw[key], list):
            # 이전 형식: 직접 list → 새 형식으로 변환
            recent_games_normalized[key] = {
                "recent_games": recent_games_raw[key],
                "highest_hu": None,
            }
        else:
            # 새로운 형식: 그대로 사용
            recent_games_normalized[key] = recent_games_raw[key]
    
    return {
        "nickname": account.get("nickname") or payload.get("nickname"),
        "account_id": account.get("account_id"),
        "avatar": account.get("avatar", {}),
        "updated_at": payload.get("updated_at"),
        "rank_4p": account.get("rank_4p", {}),
        "rank_3p": account.get("rank_3p", {}),
        "achievement_total": (account.get("achievement") or {}).get("total"),
        "recent_games": recent_games_normalized,
        # 즐겨찾기(하이라이트) 정보 추가
        "favorite_hu": account.get("favorite_hu", []),
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
    avatar_base = str(int(avatar_id)) if avatar_id else "0"
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
    mahjong_category: int  # 1 for 4-player, 2 for 3-player
) -> str:
    nickname = escape(str(profile.get("nickname") or "Unknown"))
    avatar = profile.get("avatar") or {}
    avatar_id = int(avatar.get("avatar_id") or 0)
    avatar_base = str(avatar_id) if avatar_id else "-"
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

    visible_stars = min(max(star, 0), 3)
    # 별을 하나씩 나타나도록 SVG 생성 (중앙 정렬)
    stars_svg = ""
    star_width = 15  # 각 별의 너비
    total_width = visible_stars * star_width
    center_x = 268
    start_x = center_x - (total_width / 2)
    
    for i in range(visible_stars):
        delay = 1.1 + (i * 0.15)
        star_x = start_x + (i * star_width) + (star_width / 2)
        stars_svg += f"<text x='{star_x:.1f}' y='38' fill='#fff4c5' font-size='16' text-anchor='middle' font-family='Segoe UI, Malgun Gothic, sans-serif' opacity='0'>★<animate attributeName='opacity' from='0' to='1' dur='0.2s' begin='{delay}s' fill='freeze'/></text>"
    
    star_text = ""  # 더 이상 사용 안 함

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
            f"<rect x='{gx}' y='{gy}' width='0' height='{gh}' rx='4' fill='{gauge_color}' fill-opacity='0.85'>"
            f"<animate attributeName='width' from='0' to='{fill_w:.1f}' dur='0.8s' begin='1.1s' fill='freeze'/>"
            f"</rect>"
            f"<text x='{gx + gw / 2 - 1}' y='{gy - 10}' text-anchor='middle' fill='rgba(234,255,242,0.88)' font-size='14' "
            f"font-family='Segoe UI, Malgun Gothic, sans-serif'>{score_int}/{cap_score} </text>"
        )

    category_data = (profile.get("recent_games") or {}).get(recent_key) or {}
    
    # 하위 호환성: 기존 형식(list)과 새로운 형식(dict) 모두 지원
    if isinstance(category_data, list):
        # 이전 형식: 직접 list
        recent_games = category_data[:10]
        highest_hu = None
    else:
        # 새로운 형식: dict with recent_games and highest_hu
        raw_games = category_data.get("recent_games") or []
        # 등급전(game_category=2) 데이터만 필터링하여 그래프에 표시
        # game_category 필드가 없는 경우(구 데이터)는 등급전으로 간주(2)
        recent_games = [g for g in raw_games if g.get("game_category", 2) == 2][:10]
        highest_hu = category_data.get("highest_hu")
    
    # 즐겨찾기(Favorite Hu) 확인: 해당 모드(mahjong_category)에 맞는 첫 번째 즐겨찾기가 있으면 highest_hu 대체
    favorite_hu_list = profile.get("favorite_hu", [])
    for fav in favorite_hu_list:
        # fav.category 1=4p, 2=3p
        if fav.get("category") == mahjong_category:
            highest_hu = fav.get("hu")
            break
    
    # recent list is latest-first in current payload; reverse so latest appears on the right side.
    recent_games = list(reversed(recent_games))
    ranks = []
    for item in recent_games:
        if not isinstance(item, dict):
            continue
        value = int(item.get("rank", max_rank))
        ranks.append(max(1, min(max_rank, value)))

    # Chart 관련 변수 (y 좌표를 아래로 조정하여 공간 확보)
    chart_x = 40
    chart_y = 135
    chart_w = 390
    chart_h = 50

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
        for idx, (x, y) in enumerate(coords):
            delay = 1.3 + (idx * 0.15)  # 각 점마다 지연
            point_dots += f"""<circle cx='{x:.1f}' cy='{y:.1f}' r='3.6' fill='#fff6b0' stroke='#ffffff' stroke-width='1.2' opacity='0'>
      <animate attributeName='opacity' values='0;1;1' keyTimes='0;0.5;1' dur='0.8s' begin='{delay}s' fill='freeze'/>
      <animate attributeName='r' values='1.2;5.5;3.6' keyTimes='0;0.5;1' dur='0.8s' begin='{delay}s' fill='freeze'/>
    </circle>"""

    # 마작 타일을 SVG로 그리는 함수
    def tile_int_to_code(tile_int):
        """정수 타일값을 "5m" 형식의 코드로 변환 (적도는 "5m_red")
        
        Majsoul 타일 인코딩:
        0-8:   1m-9m
        9-17:  1p-9p
        18-26: 1s-9s
        27-33: 1z-7z
        0x10 비트: 적패(빨간 5) 플래그
        """
        # 정수가 아닌 경우 (이미 문자열이면 그대로 반환)
        if isinstance(tile_int, str):
            # 적도패(0m, 0p, 0s) 처리
            if tile_int == "0m": return "5m_red"
            if tile_int == "0p": return "5p_red"
            if tile_int == "0s": return "5s_red"
            return tile_int
        
        tile_int = int(tile_int)
        
        # 적패(빨간 5) 플래그 확인 (0x10 비트)
        is_red = (tile_int & 0x10) != 0
        tile_int = tile_int & 0x0F  # 플래그 제거
        
        # 기본 타일 코드 계산
        if 0 <= tile_int <= 8:
            num = tile_int + 1
            suit = 'm'
        elif 9 <= tile_int <= 17:
            num = tile_int - 9 + 1
            suit = 'p'
        elif 18 <= tile_int <= 26:
            num = tile_int - 18 + 1
            suit = 's'
        elif 27 <= tile_int <= 33:
            num = tile_int - 27 + 1
            suit = 'z'
        else:
            return ""
        
        # 5m, 5p, 5s는 적도 여부에 따라 구분
        tile_code = f"{num}{suit}"
        if is_red and num == 5 and suit in ['m', 'p', 's']:
            tile_code = f"{num}{suit}_red"
        
        return tile_code
    
    def render_tile_svg(tile_code, x: int, y: int, w: int = 20, h: int = 28) -> str:
        """마작 타일 이미지를 SVG에 삽입
        tile_code: "4m", "6p", "5s", "1z" 형태 또는 정수
        """
        # 정수면 코드로 변환
        tile_code = tile_int_to_code(tile_code)
        
        if not tile_code or len(tile_code) < 2:
            return ""
        
        import base64
        import os
        
        # 타일 이미지 파일 경로
        tile_image_path = os.path.join(os.path.dirname(__file__), 'assets', 'tiles', f'{tile_code}.png')
        
        # 파일이 존재하면 base64로 인코딩
        if os.path.exists(tile_image_path):
            try:
                with open(tile_image_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                # 타일 이미지 SVG에 삽입
                return f'<image href="data:image/png;base64,{image_data}" x="{x}" y="{y}" width="{w}" height="{h}"/>'
            except Exception as e:
                print(f"타일 이미지 로드 실패 {tile_code}: {e}")
        
        # 폴백: 이미지 없으면 텍스트로 표시
        num = tile_code[:-1]
        suit = tile_code[-1]
        colors = {
            'm': '#E53935',    # 맨즈: 빨강
            'p': '#FDD835',    # 핀즈: 노랑
            's': '#43A047',    # 소즈: 초록
            'z': '#424242',    # 자패: 검정
        }
        color = colors.get(suit, '#666')
        text_color = 'white' if suit in ['m', 'z'] else 'black'
        font_sz = int(h * 0.4)
        
        return f'''<g>
<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{color}" stroke="rgba(255,255,255,0.3)" stroke-width="0.5"/>
<text x="{x+w/2}" y="{y+h*0.75}" text-anchor="middle" font-size="{font_sz}" font-weight="bold" fill="{text_color}" font-family="Arial, sans-serif">{num}</text>
</g>'''
    
    # 최고 패 정보 포매팅 (위치를 차트 바로 위로)
    highest_hu_svg = ""
    if highest_hu:
        hands = highest_hu.get("hands", [])
        ming = highest_hu.get("ming", [])
        hupai = highest_hu.get("hupai", "")
        
        if hands:
            # 타일 SVG 생성
            tiles_svg = ""
            
            # "최고 화료" 라벨은 생략하거나 작게 표시 (공간 문제)
            # tiles_svg += ...
            
            x_pos = 16
            # 차트가 135부터 시작하므로, 그 바로 위인 100~130 영역 사용
            # 타일 높이 28px
            base_y = 95
            
            # (1) 배치 계산: 타일 개수 확인 및 스케일 조정
            parsed_ming = []
            if ming:
                for m in ming:
                    if '(' in m and m.endswith(')'):
                        content = m[m.find('(')+1:-1]
                        parts = [t.strip() for t in content.split(',') if t.strip()]
                        parsed_ming.extend(parts)
                    else:
                        parsed_ming.append(m)

            count_hands = len(hands)
            count_ming = len(parsed_ming)
            count_hupai = 1 if hupai else 0
            
            # 기본값
            default_w = 20
            default_h = 28
            default_spacing = 22
            ref_group_gap = 10
            
            # 정확한 너비 계산
            req_width = (count_hands * default_spacing)
            if count_ming > 0:
                req_width += int(ref_group_gap * 0.5) + (count_ming * default_spacing)
            if count_hupai > 0:
                req_width += int(ref_group_gap * 0.8) + (count_hupai * default_spacing)
            
            # 마지막 타일의 여백(spacing - w)을 제외하면 조금 더 공간 확보 가능하지만
            # 계산 단순화를 위해 포함하되 여유 공간을 둠
            
            # 사용 가능 너비: 전체 너비 450 중 좌우 여백(약 16~20px씩) 제외
            avail_width = 414
            
            scale = 1.0
            if req_width > avail_width:
                scale = avail_width / req_width
                scale *= 0.98  # 약간의 여유
            
            # 스케일 적용 (너무 작아지지 않도록 하한선은 두되, 18개 이상일 경우 더 줄어들 수 있게 0.5로 완화)
            scale = max(scale, 0.5)
            
            tile_w = int(default_w * scale)
            tile_h = int(default_h * scale)
            spacing = int(default_spacing * scale)
            
            # 그룹 간격도 스케일링
            ming_gap_px = int(ref_group_gap * 0.5 * scale)
            hu_gap_px = int(ref_group_gap * 0.8 * scale)
            
            # 위치 미세 조정 (작아진 만큼 라인 중앙 정렬)
            base_y = 95 + (28 - tile_h) // 2 
            
            # (2) 렌더링
            # 손패 타일들
            for tile in hands:
                tiles_svg += render_tile_svg(tile, x_pos, base_y, tile_w, tile_h)
                x_pos += spacing
            
            # 운 패 (밍패) - | 대신 공백 사용
            if parsed_ming:
                x_pos += ming_gap_px
                for tile in parsed_ming:
                    tiles_svg += render_tile_svg(tile, x_pos, base_y, tile_w, tile_h)
                    x_pos += spacing
            
            # 쯔모/론 패 - + 대신 공백 사용
            if hupai:
                x_pos += hu_gap_px
                tiles_svg += render_tile_svg(hupai, x_pos, base_y, tile_w, tile_h)
            
            highest_hu_svg = tiles_svg
    
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
    <clipPath id='avatarClip'>
        <rect x='20' y='20' width='64' height='64' rx='12'/>
    </clipPath>
  </defs>
    <rect width='450' height='200' rx='16' fill='url(#g)'/>
        <rect x='8' y='8' width='434' height='184' rx='12' fill='{theme["panel"]}'/>
    <!-- Profile Section -->
    <g opacity='0'>
      <animate attributeName='opacity' from='0' to='1' dur='0.5s' begin='0s' fill='freeze'/>
      <rect x='16' y='16' width='72' height='72' rx='14' fill='rgba(255,255,255,0.20)' stroke='rgba(255,255,255,0.50)'/>
      <image x='20' y='20' width='64' height='64' href='{avatar_data_uri}' preserveAspectRatio='xMidYMid slice' clip-path='url(#avatarClip)'/>
      <text x='96' y='48' fill='#ffffff' font-size='28' font-family='Segoe UI, Malgun Gothic, sans-serif' font-weight='700'>{nickname}</text>
      <text x='16' y='20' fill='#f8fff9' font-size='8' text-anchor='start' font-family='Segoe UI, Malgun Gothic, sans-serif'>{escape(avatar_text)}</text>
      <text x='96' y='84' fill='#eafff2' font-size='20' font-family='Segoe UI, Malgun Gothic, sans-serif'>{escape(subtitle1)}</text>
    </g>
    <!-- Rank Section - Background & Gauge -->
    <g opacity='0'>
      <animate attributeName='opacity' from='0' to='1' dur='0.3s' begin='0.4' fill='freeze'/>
      <rect x='230' y='22' width='76' height='24' rx='12' fill='rgba(255,255,255,0.22)' stroke='rgba(255,255,255,0.48)'/>
      {gauge_svg}
    </g>
    <!-- Rank Section - Image -->
    <g opacity='0'>
      <animate attributeName='opacity' from='0' to='1' dur='0.3s' begin='0.8s' fill='freeze'/>
      <rect x='337' y='15' width='94' height='94' rx='12' fill='rgba(255,255,255,0.18)' stroke='rgba(255,255,255,0.45)'/>
      <image x='340' y='17' width='90' height='90' href='{icon_data_uri}' preserveAspectRatio='xMidYMid meet'/>
    </g>
    <!-- Stars -->
    {stars_svg}
    <!-- Chart Section -->
    <g opacity='0'>
      <animate attributeName='opacity' from='0' to='1' dur='0.3s' begin='1s' fill='freeze'/>
      {highest_hu_svg}
      <rect x='{chart_x}' y='{chart_y}' width='{chart_w}' height='{chart_h}' rx='8' fill='rgba(255,255,255,0.14)'/>
      {rank_grid_lines}
      {rank_labels}
    </g>
    <!-- Graph Line and Points -->
    <polyline points='{polyline}' fill='none' stroke='url(#lineg)' stroke-width='3' stroke-linecap='round' stroke-linejoin='round' stroke-dasharray='1000' stroke-dashoffset='1000'>
      <animate attributeName='stroke-dashoffset' from='1000' to='0' dur='3s' begin='1.3s' fill='freeze'/>
    </polyline>
    {point_dots}
</svg>"""


def _build_badge_svg(profile: dict) -> str:
    return _build_badge_svg_mode(
        profile=profile,
        rank_key="rank_4p",
        recent_key="four_player",
        mode_label="4인",
        max_rank=4,
        icon_data_uri = _rank_icon_data_uri(int((profile.get("rank_4p") or {}).get("tier") or 0)),
        mahjong_category=1
    )
    
def _build_badge3_svg(profile: dict) -> str:
    return _build_badge_svg_mode(
        profile=profile,
        rank_key="rank_3p",
        recent_key="three_player",
        mode_label="3인",
        max_rank=3,
        icon_data_uri = _3rank_icon_data_uri(int((profile.get("rank_3p") or {}).get("tier") or 0)),
        mahjong_category=2
    )


def _badge_response(request: Request, svg: str, updated_at: str) -> Response:
    """ETag/Last-Modified 조건부 요청을 처리하여 304 or 200 반환."""
    etag = '"' + hashlib.md5(svg.encode()).hexdigest() + '"'
    try:
        dt = datetime.fromisoformat(updated_at)
        last_modified = formatdate(dt.timestamp(), usegmt=True)
    except Exception:
        last_modified = formatdate(usegmt=True)

    headers = {
        # max-age=1800: 브라우저 30분 캐시
        # s-maxage=1800: GitHub Camo 등 CDN 프록시 30분마다 재검증 (mazassumnida 방식)
        # stale-while-revalidate=60: 재검증 중에도 기존 캐시 즉시 반환
        "Cache-Control": "max-age=1800, s-maxage=1800, stale-while-revalidate=60",
        "ETag": etag,
        "Last-Modified": last_modified,
    }

    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304, headers=headers)

    return Response(content=svg, media_type="image/svg+xml", headers=headers)


@app.get("/api/player/{nickname}/badge.svg")
async def get_player_badge_svg(request: Request, nickname: str, refresh: bool = Query(default=False)):
    payload = await _load_or_auto_sync(nickname, force=refresh)
    profile = _build_public_profile(payload)
    svg = _build_badge_svg(profile)
    return _badge_response(request, svg, payload.get("updated_at", ""))


@app.get("/api/player/{nickname}/badge3.svg")
async def get_player_badge3_svg(request: Request, nickname: str, refresh: bool = Query(default=False)):
    payload = await _load_or_auto_sync(nickname, force=refresh)
    profile = _build_public_profile(payload)
    svg = _build_badge3_svg(profile)
    return _badge_response(request, svg, payload.get("updated_at", ""))



# --- 짧은 alias URL (GitHub README 임베드용) ---

@app.get("/badge/{nickname}")
async def get_badge_short(request: Request, nickname: str, refresh: bool = Query(default=False)):
    payload = await _load_or_auto_sync(nickname, force=refresh)
    profile = _build_public_profile(payload)
    svg = _build_badge_svg(profile)
    return _badge_response(request, svg, payload.get("updated_at", ""))


@app.get("/badge3/{nickname}")
async def get_badge3_short(request: Request, nickname: str, refresh: bool = Query(default=False)):
    payload = await _load_or_auto_sync(nickname, force=refresh)
    profile = _build_public_profile(payload)
    svg = _build_badge3_svg(profile)
    return _badge_response(request, svg, payload.get("updated_at", ""))


# --- 디버그: 저장된 raw 데이터 확인 ---

from fastapi.responses import JSONResponse

@app.get("/api/debug/{nickname}")
async def debug_player_data(nickname: str):
    """저장된 JSON 데이터를 그대로 반환 (recent_games 구조 확인용)."""
    account_id = _find_account_id_by_nickname(nickname)
    if account_id is None:
        raise HTTPException(status_code=404, detail="Not found in index")
    file_path = _player_file(account_id)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Data file not found")
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    recent = raw.get("summary", {}).get("recent_games", {})
    
    def extract_data(category_data):
        """이전 형식(list)과 새로운 형식(dict) 모두 지원"""
        if isinstance(category_data, list):
            # 이전 형식: 직접 list
            return {
                "count": len(category_data),
                "highest_hu": None,
                "sample": category_data[:3],
            }
        else:
            # 새로운 형식: dict with recent_games and highest_hu
            return {
                "count": len(category_data.get("recent_games") or []),
                "highest_hu": category_data.get("highest_hu"),
                "sample": (category_data.get("recent_games") or [])[:3],
            }
    
    return JSONResponse({
        "updated_at": raw.get("updated_at"),
        "nickname": raw.get("nickname"),
        "four_player": extract_data(recent.get("four_player") or []),
        "three_player": extract_data(recent.get("three_player") or []),
    })
