"""amae-koromo 공개 API를 통해 플레이어 데이터를 가져오는 클라이언트.

로그인 불필요 - 마작소울 인증 없이 동작.
"""

import time
import urllib.parse
from datetime import datetime, timezone

import aiohttp

# 4P: 5-data.amae-koromo.com / 3P: ak-data-1.sapk.ch
_BASE4 = "https://5-data.amae-koromo.com/api/v2/pl4"
_BASE3 = "https://ak-data-1.sapk.ch/api/v2/pl3"

# amae-koromo 가 다루는 4P 등급전 모드 ID (金の間 동/서, 玉の間 동/서, 王座の間 동/서)
_MODES_4P = "9,8,12,11,16,15"
_MODES_3P = "22,21,24,23,26,25"

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
    tier = (level_id // 100) % 100
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
    async with session.get(url) as r:
        if r.status != 200:
            return None
        data = await r.json()
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
    async with session.get(url) as r:
        if r.status != 200:
            return None
        return await r.json()


async def _fetch_records(
    session: aiohttp.ClientSession,
    account_id: int,
    base: str,
    modes: str,
    limit: int = 10,
) -> list:
    """최근 게임 기록. 순서는 오래된 것 → 최신."""
    end_t = int(time.time()) + 86400
    start_t = end_t - 86400 * 365 * 2
    url = f"{base}/player_records/{account_id}/{start_t}/{end_t}?limit={limit}&mode={modes}"
    async with session.get(url) as r:
        if r.status != 200:
            return []
        data = await r.json()
        return data if isinstance(data, list) else []


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
        result.append({
            "rank": min(rank, max_rank),
            "final_point": next(
                (p.get("score", 0) for p in rec.get("players", []) if p.get("accountId") == account_id),
                0,
            ),
            "game_category": 2,  # 등급전
            "start_time": rec.get("startTime"),
            "mode_id": rec.get("modeId"),
        })
    return result


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
        if player_4p is None:
            # stats에서 level/score 가져오기
            stats_4p = await _fetch_stats(session, account_id, _BASE4, _MODES_4P)
        else:
            stats_4p = player_4p  # search 결과에 level 포함

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

        # ── 최근 4P 게임 기록 ────────────────────────────────────────
        # played_modes 가 있으면 그 모드만, 없으면 전체 모드 시도
        played_modes = stats_4p.get("played_modes") if isinstance(stats_4p, dict) else None
        if played_modes:
            modes_str = ",".join(str(m) for m in played_modes)
        else:
            modes_str = _MODES_4P

        records_4p = await _fetch_records(session, account_id, _BASE4, modes_str, recent_count)
        recent_4p = _records_to_recent_games(records_4p, account_id, 4)

        # ── 최근 3P 게임 기록 ────────────────────────────────────────
        played_modes_3p = stats_3p.get("played_modes") if isinstance(stats_3p, dict) else None
        if played_modes_3p:
            modes3_str = ",".join(str(m) for m in played_modes_3p)
        else:
            modes3_str = _MODES_3P
        records_3p = await _fetch_records(session, account_id, _BASE3, modes3_str, recent_count)
        recent_3p = _records_to_recent_games(records_3p, account_id, 3)

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
        "source": "amae-koromo",
        "meta": {
            "queried_at": queried_at,
            "host": "amae-koromo",
            "auth_method": "none",
        },
    }
