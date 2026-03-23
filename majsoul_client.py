import hashlib
import hmac
import random
import uuid
from datetime import datetime, timezone

import aiohttp

import ms.protocol_pb2 as pb
from ms.base import MSRPCChannel
from ms.rpc import Lobby

MS_HOST = "https://game.maj-soul.com"

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


def _build_rank_info(rank_id: int, score: int) -> dict:
    tier = (rank_id // 100) % 100
    star = rank_id % 100
    tier_name_ko = RANK_TIER_NAMES_KO.get(tier, "미확인")
    tier_name_en = RANK_TIER_NAMES_EN.get(tier, "Unknown")

    return {
        "id": rank_id,
        "score": score,
        "tier": tier,
        "star": star,
        "name_ko": f"{tier_name_ko} {star}",
        "name_en": f"{tier_name_en} {star}",
    }


async def connect():
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{MS_HOST}/1/version.json") as res:
            version = (await res.json())["version"]
            version_to_force = version.replace(".w", "")

        async with session.get(f"{MS_HOST}/1/v{version}/config.json") as res:
            config = await res.json()

            route_urls = []
            for entry in config.get("ip", []):
                for field in ("region_urls", "gateways"):
                    for route in entry.get(field, []):
                        if isinstance(route, dict) and route.get("url"):
                            route_urls.append(route["url"])

            if not route_urls:
                raise RuntimeError(f"No route URLs found in config ip section: {config.get('ip')}")

            random.shuffle(route_urls)

        endpoint = None
        for url in route_urls:
            try:
                async with session.get(url + "?service=ws-gateway&protocol=ws&ssl=true") as res:
                    servers = await res.json()
                    server_candidates = servers.get("servers", []) if isinstance(servers, dict) else []
                    if not server_candidates:
                        raise RuntimeError("No websocket servers returned")

                    server = random.choice(server_candidates)
                    if isinstance(server, dict):
                        server = server.get("url") or server.get("host") or server.get("server")
                    if not server:
                        raise RuntimeError("Invalid server entry")

                    if server.startswith("ws://") or server.startswith("wss://"):
                        endpoint = server.rstrip("/")
                    elif server.startswith("http://") or server.startswith("https://"):
                        endpoint = server.replace("https://", "wss://").replace("http://", "ws://").rstrip("/")
                    else:
                        endpoint = f"wss://{server}"

                    if not endpoint.endswith("/gateway"):
                        endpoint = endpoint + "/gateway"
                    break
            except Exception:
                endpoint = url.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + "/gateway"
                break

        if not endpoint:
            raise RuntimeError("Unable to resolve websocket endpoint")

    channel = MSRPCChannel(endpoint)
    lobby = Lobby(channel)
    await channel.connect(MS_HOST)
    return lobby, channel, version_to_force


async def login(lobby, username, password, version_to_force):
    req = pb.ReqLogin()
    req.account = username
    req.password = hmac.new(b"lailai", password.encode(), hashlib.sha256).hexdigest()
    req.device.is_browser = True
    req.random_key = str(uuid.uuid1())
    req.gen_access_token = True
    req.client_version_string = f"web-{version_to_force}"
    req.currency_platforms.append(2)

    res = await lobby.login(req)
    if not res.access_token:
        raise RuntimeError(
            f"Login failed: code={res.error.code}, u32={list(res.error.u32_params)}, str={list(res.error.str_params)}"
        )

    return res.account_id


async def resolve_account_id_by_nickname(lobby, nickname):
    req = pb.ReqSearchAccountByPattern()
    req.search_next = False
    req.pattern = nickname
    res = await lobby.search_account_by_pattern(req)

    if res.error.code:
        raise RuntimeError(f"search_account_by_pattern failed: code={res.error.code}")

    candidates = list(res.match_accounts)
    if res.decode_id and res.decode_id not in candidates:
        candidates.insert(0, res.decode_id)

    if not candidates:
        raise RuntimeError(f"No account found for nickname pattern: {nickname}")

    for candidate_id in candidates[:20]:
        id_req = pb.ReqSearchAccountById()
        id_req.account_id = candidate_id
        id_res = await lobby.search_account_by_id(id_req)
        if id_res.error.code:
            continue
        if id_res.player.nickname == nickname:
            return candidate_id

    return candidates[0]


def _parse_highest_hu_record(hu):
    """protobuf HighestHuRecord -> dict"""
    if not hu:
        return None
    try:
        # 데이터 유효성 검사: title이나 title_id 둘 중 하나라도 있으면 유효
        if not (hu.title or hu.title_id):
            return None
        
        # 안전한 데이터 추출
        result = {
            "fanshu": int(hu.fanshu) if hu.fanshu else 0,
            "doranum": int(hu.doranum) if hu.doranum else 0,
            "title": str(hu.title) if hu.title else "",
            "title_id": int(hu.title_id) if hu.title_id else 0,
            "hands": list(hu.hands) if hu.hands else [],
            "ming": list(hu.ming) if hu.ming else [],
            "hupai": str(hu.hupai) if hu.hupai else "",
        }
        
        # 유효한 데이터 확인: title이 있으면 반환
        if result.get("title"):
            return result
        # title이 없지만 title_id가 있으면 반환
        elif result.get("title_id"):
            return result
        else:
            return None
    except Exception:
        return None


def build_account_summary(account_info_res):
    account = account_info_res.account
    achievement_total = sum(item.count for item in account.achievement_count)
    achievement_by_rare = {str(item.rare): item.count for item in account.achievement_count}

    # 프로필에 설정된 하이라이트(즐겨찾기) 화료 정보 추출 - 등급전(type=2)만 가져오기
    favorites = []
    if hasattr(account, 'favorite_hu'):
        for fav in account.favorite_hu:
            # 등급전(type=2)으로 설정된 하이라이트만 포함
            if fav.type != 2:
                continue
            hu_data = _parse_highest_hu_record(fav.hu)
            if hu_data:
                favorites.append({
                    "category": fav.category,  # 1: 4인, 2: 3인
                    "mode": fav.mode,
                    "type": fav.type,
                    "hu": hu_data
                })

    return {
        "account_id": account.account_id,
        "nickname": account.nickname,
        "avatar": {
            "avatar_id": account.avatar_id,
            "avatar_frame": account.avatar_frame,
        },
        "rank_4p": _build_rank_info(account.level.id, account.level.score),
        "rank_3p": _build_rank_info(account.level3.id, account.level3.score),
        "achievement": {"total": achievement_total, "by_rare": achievement_by_rare},
        "favorite_hu": favorites,
    }


def build_recent_from_statistics(stat_res, recent_count):
    queried_at = datetime.now(timezone.utc)
    queried_at_iso = queried_at.isoformat()
    queried_date = queried_at.date().isoformat()

    def block_score(data):
        return (
            data.statistic.recent_round.total_count,
            len(data.statistic.recent_10_game_result),
        )

    def items_from_block(data):
        items = []
        for game_result in reversed(data.statistic.recent_10_game_result):
            items.append(
                {
                    "mahjong_category": data.mahjong_category,
                    "game_category": data.game_category,
                    "rank": game_result.rank,
                    "final_point": game_result.final_point,
                    "date": queried_date,
                    "queried_at": queried_at_iso,
                }
            )
        return items

    def highest_hu_from_block(data):
        """최고 패 정보 추출 (실제 API 데이터 우선, 없으면 None)"""
        if not data or not data.statistic:
            return None
        
        # highest_hu 필드 존재 여부 확인
        if not hasattr(data.statistic, 'highest_hu') or not data.statistic.highest_hu:
            return None
        
        return _parse_highest_hu_record(data.statistic.highest_hu)

    by_category = {}

    for stat_data in stat_res.statistic_data:
        category = stat_data.mahjong_category
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(stat_data)

    recent_4p = []
    recent_3p = []
    unknown = []
    highest_hu_4p = None
    highest_hu_3p = None

    for category, blocks in by_category.items():
        # 등급전(game_category == 2) 데이터만 필터링
        blocks = [b for b in blocks if getattr(b, 'game_category', 0) == 2]
        if not blocks:
            continue

        # 가장 많이 플레이한 블록을 기준으로 highest_hu 추출
        primary = max(blocks, key=block_score)
        
        # 게임 기록은 모든 블록에서 수집
        all_items = []
        for block in blocks:
            all_items.extend(items_from_block(block))

        if category == 1:
            recent_4p = all_items
            highest_hu_4p = highest_hu_from_block(primary)
        elif category == 2:
            recent_3p = all_items
            highest_hu_3p = highest_hu_from_block(primary)
        else:
            unknown.extend(all_items)

    return {
        "four_player": {
            "recent_games": recent_4p[:recent_count],
            "highest_hu": highest_hu_4p,
        },
        "three_player": {
            "recent_games": recent_3p[:recent_count],
            "highest_hu": highest_hu_3p,
        },
        "unknown": {
            "recent_games": unknown[:recent_count],
            "highest_hu": None,
        },
    }


async def build_summary(lobby, target_account_id, recent_count):
    account_req = pb.ReqAccountInfo()
    account_req.account_id = target_account_id
    account_info_res = await lobby.fetch_account_info(account_req)

    stat_req = pb.ReqAccountStatisticInfo()
    stat_req.account_id = target_account_id
    stat_res = await lobby.fetch_account_statistic_info(stat_req)

    if stat_res.error.code:
        raise RuntimeError(f"fetch_account_statistic_info failed: code={stat_res.error.code}")

    queried_at_iso = datetime.now(timezone.utc).isoformat()

    return {
        "account": build_account_summary(account_info_res),
        "recent_games": build_recent_from_statistics(stat_res, recent_count),
        "source": "fetchAccountStatisticInfo",
        "meta": {
            "queried_at": queried_at_iso,
            "date_note": "fetchAccountStatisticInfo recent_10_game_result does not include per-game datetime; date fields are query-time values.",
        },
    }


async def fetch_summary(username, password, target_nickname=None, recent_count=10):
    recent_count = max(1, min(recent_count or 10, 30))
    lobby, channel, version_to_force = await connect()
    try:
        login_account_id = await login(lobby, username, password, version_to_force)
        if (target_nickname or "").strip():
            resolved_account_id = await resolve_account_id_by_nickname(lobby, target_nickname.strip())
        else:
            resolved_account_id = login_account_id

        summary = await build_summary(lobby, resolved_account_id, recent_count)
        summary["meta"]["requested_recent_count"] = recent_count
        return summary
    finally:
        await channel.close()
