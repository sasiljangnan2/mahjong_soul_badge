"""amae-koromo 공개 API를 통해 플레이어 데이터를 가져오는 클라이언트.

로그인 불필요 - 마작소울 인증 없이 동작.
"""

import asyncio
import os
import time
import urllib.parse
from datetime import datetime, timezone

import aiohttp

# 4P와 3P 모두 같은 현재 amae-koromo 미러를 사용한다.
# 발급된 Bearer token은 이 호스트의 보호된 player_records에 적용된다.
_BASE4 = "https://5-data.amae-koromo.com/api/v2/pl4"
_BASE3 = "https://5-data.amae-koromo.com/api/v2/pl3"

# amae-koromo 가 다루는 4P 등급전 모드 ID (金の間 동/서, 玉の間 동/서, 王座の間 동/서)
_MODES_4P = "9,8,12,11,16,15"
_MODES_3P = "22,21,24,23,26,25"
def _normalize_api_token(value: str) -> str:
    """환경변수에 raw token 또는 'Authorization: Bearer ...'를 넣어도 처리한다."""
    token = (value or "").strip().strip('"').strip("'")
    if token.lower().startswith("authorization:"):
        token = token.split(":", 1)[1].strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


_API_TOKEN = _normalize_api_token(
    os.environ.get("AMAE_API_TOKEN") or os.environ.get("AMAE_CAP_TOKEN", "")
)
_REQUEST_LOCK = asyncio.Lock()
_LAST_REQUEST_AT = 0.0


async def _api_get(
    session: aiohttp.ClientSession,
    url: str,
    *,
    authenticated: bool = False,
) -> tuple[int, object | None, str]:
    """Bearer 인증을 적용하고 프로세스 전체 요청 속도를 최대 1 QPS로 제한한다."""
    global _LAST_REQUEST_AT

    headers = {"Authorization": f"Bearer {_API_TOKEN}"} if authenticated and _API_TOKEN else {}
    async with _REQUEST_LOCK:
        wait_seconds = 1.0 - (time.monotonic() - _LAST_REQUEST_AT)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

        try:
            async with session.get(url, headers=headers) as response:
                body = await response.text()
                data = None
                if response.status == 200:
                    try:
                        data = await response.json()
                    except (aiohttp.ContentTypeError, ValueError):
                        pass
                return response.status, data, body
        finally:
            _LAST_REQUEST_AT = time.monotonic()

RANK_TIER_NAMES_KO = {
    1: "초심",
    2: "작사",
    3: "작걸",
    4: "작호",
    5: "작성",
    6: "혼천",
}
RANK_TIER_NAMES_EN = {
    1: "Novice",
    2: "Adept",
    3: "Expert",
    4: "Master",
    5: "Saint",
    6: "Celestial",
}


def _build_rank_info(level_id: int, score: int) -> dict:
    raw_tier = (level_id // 100) % 100
    # amae-koromo에서 혼천은 10701~10720 형식이다. 배지 내부의
    # tier 6(혼천) 테마/아이콘에 연결하고 끝 두 자리는 혼천 레벨로 쓴다.
    tier = 6 if raw_tier >= 6 else raw_tier
    star = level_id % 100
    tier_name_ko = RANK_TIER_NAMES_KO.get(tier, "미확인")
    tier_name_en = RANK_TIER_NAMES_EN.get(tier, "Unknown")
    return {
        "id": level_id,
        "score": score,
        "tier": tier,
        "star": star,
        "name_ko": f"{tier_name_ko} {star}",
        "name_en": f"{tier_name_en} {star}",
    }


async def _search_player(session: aiohttp.ClientSession, nickname: str, base: str) -> dict | None:
    """닉네임으로 플레이어 검색. 없으면 None."""
    encoded = urllib.parse.quote(nickname)
    url = f"{base}/search_player/{encoded}"
    status, data, _ = await _api_get(session, url)
    if status != 200:
        return None
    if not data:
        return None
    # 정확히 일치하는 닉네임 우선
    for item in data:
        if item.get("nickname") == nickname:
            return item
    return data[0]


async def _fetch_stats(session: aiohttp.ClientSession, account_id: int, base: str, modes: str) -> dict | None:
    """플레이어 전체 통계 (레벨/점수 포함)."""
    end_t = int(time.time()) + 86400
    start_t = end_t - 86400 * 365 * 2  # 2년치
    url = f"{base}/player_stats/{account_id}/{start_t}/{end_t}?mode={modes}"
    status, data, _ = await _api_get(session, url)
    return data if status == 200 and isinstance(data, dict) else None


async def _fetch_records(
    session: aiohttp.ClientSession,
    account_id: int,
    base: str,
    modes: str,
    start_t: int,
    end_t: int,
    limit: int = 500,
) -> tuple[list, str | None]:
    """지정한 기간의 게임 기록을 가져온다."""
    url = f"{base}/player_records/{account_id}/{start_t}/{end_t}?limit={limit}&mode={modes}"
    status, data, body = await _api_get(session, url, authenticated=True)
    if status != 200:
        detail = body.strip().replace("\n", " ")[:200]
        return [], f"HTTP {status}: {detail}"
    return (data if isinstance(data, list) else []), None


async def _fetch_latest_records(
    session: aiohttp.ClientSession,
    account_id: int,
    base: str,
    modes: str,
    count: int,
    latest_timestamp: int | None = None,
) -> tuple[list, str | None]:
    """API가 오래된 기록부터 반환해도 실제 최신 count개를 선별한다."""
    anchor = int(latest_timestamp or time.time())
    window = 86400 * 7
    max_window = 86400 * 365 * 2
    minimum_window = 3600

    while True:
        start_t = max(0, anchor - window)
        records, error = await _fetch_records(
            session,
            account_id,
            base,
            modes,
            start_t,
            anchor + 86400,
        )
        if error:
            return [], error

        # 서버 반환 한도(500개)에 걸렸다면 기간을 줄여 최신 끝부분이
        # 응답에 포함되도록 한다.
        if len(records) >= 500 and window > minimum_window:
            window = max(minimum_window, window // 2)
            continue

        if len(records) >= count or window >= max_window:
            latest = sorted(
                records,
                key=lambda record: int(record.get("startTime") or 0),
                reverse=True,
            )[:count]
            return latest, None

        window = min(max_window, window * 2)


def _rank_from_record(record: dict, account_id: int) -> int:
    """amae-koromo 기록에서 해당 플레이어의 순위(1~4) 계산 (score 내림차순)."""
    players = record.get("players", [])
    sorted_players = sorted(players, key=lambda p: p.get("score", 0), reverse=True)
    for rank, p in enumerate(sorted_players, 1):
        if p.get("accountId") == account_id:
            return rank
    return len(players)


def _records_to_recent_games(records: list, account_id: int, max_rank: int) -> list:
    """amae 기록 → 배지용 recent_games 포맷 변환."""
    result = []
    for rec in records:
        rank = _rank_from_record(rec, account_id)
        player = next(
            (p for p in rec.get("players", []) if p.get("accountId") == account_id),
            {},
        )
        result.append({
            "rank": min(rank, max_rank),
            "final_point": player.get("score", 0),
            "grading_score": player.get("gradingScore", 0),
            "game_category": 2,  # 등급전
            "start_time": rec.get("startTime"),
            "mode_id": rec.get("modeId"),
        })
    return result


def _apply_latest_grading_score(rank_info: dict, recent_games: list) -> None:
    """API 등급 점수에 가장 최근 대국의 등급 점수 증감을 반영한다."""
    base_score = int(rank_info.get("score") or 0)
    latest_delta = 0
    if recent_games:
        latest_delta = int(recent_games[0].get("grading_score") or 0)

    rank_info["base_score"] = base_score
    rank_info["latest_grading_score"] = latest_delta
    rank_info["score"] = base_score + latest_delta


async def fetch_summary(
    nickname: str | None = None,
    account_id: int | None = None,
    recent_count: int = 10,
) -> dict:
    """amae-koromo API로 플레이어 요약 정보를 가져온다.

    nickname 또는 account_id 중 하나는 필수.
    """
    recent_count = max(1, min(recent_count or 10, 30))
    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # ── account_id 확인 ──────────────────────────────────────────
        player_4p = None
        if account_id is None:
            if not nickname:
                raise ValueError("nickname 또는 account_id 필요")
            player_4p = await _search_player(session, nickname, _BASE4)
            if player_4p is None:
                raise RuntimeError(f"Player not found in amae-koromo: {nickname}")
            account_id = player_4p["id"]
        else:
            # account_id 로 직접 stats 가져오기 (search 생략)
            pass

        # ── 4P 통계 ─────────────────────────────────────────────────
        stats_4p = await _fetch_stats(session, account_id, _BASE4, _MODES_4P)

        if stats_4p is None:
            raise RuntimeError(f"Cannot fetch 4P stats for account_id={account_id}")

        level_4p = stats_4p.get("level", {})
        rank_4p = _build_rank_info(
            int(level_4p.get("id", 0)),
            int(level_4p.get("score", 0)),
        )
        actual_nickname = stats_4p.get("nickname") or nickname or str(account_id)

        # ── 3P 통계 ─────────────────────────────────────────────────
        stats_3p = await _fetch_stats(session, account_id, _BASE3, _MODES_3P)
        if stats_3p and stats_3p.get("level"):
            level_3p = stats_3p.get("level", {})
            rank_3p = _build_rank_info(
                int(level_3p.get("id", 0)),
                int(level_3p.get("score", 0)),
            )
        else:
            rank_3p = _build_rank_info(0, 0)

        # search_player의 latest_timestamp를 최신 기록 조회 기준점으로 사용한다.
        if player_4p is None and actual_nickname:
            player_4p = await _search_player(session, actual_nickname, _BASE4)
        player_3p = await _search_player(session, actual_nickname, _BASE3)

        # ── 최근 4P 게임 기록 ────────────────────────────────────────
        # played_modes 가 있으면 그 모드만, 없으면 전체 모드 시도
        played_modes = stats_4p.get("played_modes") if isinstance(stats_4p, dict) else None
        if played_modes:
            modes_str = ",".join(str(m) for m in played_modes)
        else:
            modes_str = _MODES_4P

        records_4p, records_error_4p = await _fetch_latest_records(
            session,
            account_id,
            _BASE4,
            modes_str,
            recent_count,
            int(player_4p.get("latest_timestamp", 0)) if player_4p else None,
        )
        recent_4p = _records_to_recent_games(records_4p, account_id, 4)

        # ── 최근 3P 게임 기록 ────────────────────────────────────────
        played_modes_3p = stats_3p.get("played_modes") if isinstance(stats_3p, dict) else None
        if played_modes_3p:
            modes3_str = ",".join(str(m) for m in played_modes_3p)
        else:
            modes3_str = _MODES_3P
        records_3p, records_error_3p = await _fetch_latest_records(
            session,
            account_id,
            _BASE3,
            modes3_str,
            recent_count,
            int(player_3p.get("latest_timestamp", 0)) if player_3p else None,
        )
        recent_3p = _records_to_recent_games(records_3p, account_id, 3)

        # 배지 점수 = API 등급 점수 + 가장 최근 대국의 등급 점수 증감
        _apply_latest_grading_score(rank_4p, recent_4p)
        _apply_latest_grading_score(rank_3p, recent_3p)

    queried_at = datetime.now(timezone.utc).isoformat()

    return {
        "account": {
            "account_id": account_id,
            "nickname": actual_nickname,
            "avatar": {},
            "rank_4p": rank_4p,
            "rank_3p": rank_3p,
            "achievement": {"total": 0},
            "favorite_hu": [],
        },
        "recent_games": {
            "four_player": {
                "recent_games": recent_4p[:recent_count],
                "highest_hu": None,
            },
            "three_player": {
                "recent_games": recent_3p[:recent_count],
                "highest_hu": None,
            },
            "unknown": {
                "recent_games": [],
                "highest_hu": None,
            },
        },
        "stats": {
            "four_player": {
                "count": stats_4p.get("count", 0),
                "rank_rates": stats_4p.get("rank_rates", []),
                "avg_rank": stats_4p.get("avg_rank"),
                "negative_rate": stats_4p.get("negative_rate"),
            },
            "three_player": {
                "count": stats_3p.get("count", 0) if stats_3p else 0,
                "rank_rates": stats_3p.get("rank_rates", []) if stats_3p else [],
                "avg_rank": stats_3p.get("avg_rank") if stats_3p else None,
                "negative_rate": stats_3p.get("negative_rate") if stats_3p else None,
            },
        },
        "source": "amae-koromo",
        "meta": {
            "queried_at": queried_at,
            "host": "amae-koromo",
            "auth_method": "none",
            "records": {
                "four_player": {
                    "available": records_error_4p is None,
                    "error": records_error_4p,
                },
                "three_player": {
                    "available": records_error_3p is None,
                    "error": records_error_3p,
                },
            },
        },
    }
