This repository is based on https://github.com/chaserhkj/PyMajSoul/ and provides Python wrappers for Majsoul.

It now includes an MVP API server for a Mazassumnida-like project flow:
- sync Majsoul account stats
- persist snapshot JSON locally
- read player stats through HTTP API

## Quick Start

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

### Player Query Example

`GET /api/player/{nickname}`

Example:

`GET /api/player/target_player_nickname`

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
