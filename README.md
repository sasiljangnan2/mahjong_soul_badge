This repository is based on https://github.com/chaserhkj/PyMajSoul/ and provides Python wrappers for Majsoul.

It now includes an MVP API server for a Mazassumnida-like project flow:
- sync Majsoul account stats
- persist snapshot JSON locally
- read player stats through HTTP API

## Quick Start

Windows (fastest):

```powershell
./run.ps1
```

If PowerShell execution policy blocks scripts, use:

```bat
run.bat
```

Manual way:

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run API server:

```bash
uvicorn server:app --reload
```

3. Open API docs:

`http://127.0.0.1:8000/docs`

4. Open web console (nickname sync/player test UI):

`http://127.0.0.1:8000/`

The web console now shows dashboard cards (account, rank, achievement), recent 3P/4P lists, and rank distribution bars after load.

## API Endpoints

- `GET /health`
- `POST /api/sync`
- `GET /api/player/{nickname}`
- `GET /api/player/{nickname}/public.json` (public profile JSON for embed)
- `GET /api/player/{nickname}/badge.svg` (image badge for GitHub README)
- `GET /api/player/{nickname}/badge3.svg` (3-player image badge)
- `GET /api/player/{nickname}/profile.md` (ready-to-copy markdown snippet)
- `POST /api/sync/jobs` (create auto sync job)
- `GET /api/sync/jobs` (list auto sync jobs)
- `DELETE /api/sync/jobs/{job_id}` (delete auto sync job)

### Sync Example

`POST /api/sync` body:

```json
{
	"username": "your_cn_login_account",
	"password": "your_cn_login_password",
	"target_nickname": "target_player_nickname",
	"secondary_nickname": "load_alias_nickname",
	"recent_count": 10
}
```

Synced data is saved to `data/players/{account_id}.json`.

If `target_nickname` is omitted, sync uses the logged-in account.

If `secondary_nickname` is provided, you can load the same player with that nickname alias via `GET /api/player/{nickname}`.

Rank data now includes parsed fields like `tier`, `star`, `name_ko`, and `name_en` (example: `작걸 3`).
Badge tier emblems are loaded from `assets/ranks/*.svg`.
Account data includes avatar fields, and badge currently uses only `avatar.avatar_id` (frame is not rendered).
Badge avatar image is loaded from `assets/avatars/{avatar_id_first4}.svg|png|webp|jpg` and falls back to `assets/avatars/default.svg`.

### Player Query Example

`GET /api/player/{nickname}`

Example:

`GET /api/player/target_player_nickname`

### GitHub / External Website Embed

After deployment (for example `https://your-domain.com`), use:

- Badge image: `https://your-domain.com/api/player/{nickname}/badge.svg`
- 3P Badge image: `https://your-domain.com/api/player/{nickname}/badge3.svg`
- Public JSON: `https://your-domain.com/api/player/{nickname}/public.json`
- Markdown snippet: `https://your-domain.com/api/player/{nickname}/profile.md`

GitHub README example:

```md
![Majsoul Badge](https://your-domain.com/api/player/target_player_nickname/badge.svg)
```

Website example (browser fetch):

```js
const res = await fetch("https://your-domain.com/api/player/target_player_nickname/public.json");
const profile = await res.json();
console.log(profile.rank_4p.name_ko, profile.rank_4p.score);
```

### Auto Sync Job Example

`POST /api/sync/jobs` body:

```json
{
	"username": "your_cn_login_account",
	"password": "your_cn_login_password",
	"target_nickname": "target_player_nickname",
	"secondary_nickname": "load_alias_nickname",
	"recent_count": 10,
	"interval_minutes": 10
}
```

The scheduler runs in the background while server is running and stores jobs in `data/sync_jobs.json`.

Security note: job passwords are stored in plain text in `data/sync_jobs.json` for MVP convenience.

## CLI Example

You can still use the CLI script:

```bash
python example.py -u username -p password --target-nickname nickname
```

## Notes

- Current login flow supports CN server login ID/password.
- For EN/JP, additional auth flow (email/social login) must be implemented.
- `fetchAccountStatisticInfo` does not include exact per-match datetime for recent list.

## For Developer

### Requirements

1. Install packages from `requirements.txt`
2. Install protobuf compiler

### Update Protocol Files

1. Download latest `liqi.json` and replace `ms/liqi.json`
2. `python generate_proto_file.py`
3. `protoc --python_out=. protocol.proto`
4. `chmod +x ms-plugin.py`
5. `protoc --custom_out=. --plugin=protoc-gen-custom=ms-plugin.py ./protocol.proto`
