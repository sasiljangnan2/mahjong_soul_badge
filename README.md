# Mahjong Soul Badge

amae-koromo 공개 API의 작혼 전적을 SVG 배지로 보여주는 프로젝트입니다.
![Mahjong Soul Badge](https://mahjongsoulbadge-production.up.railway.app/badge/Ssawaul)
![Mahjong Soul 3P Badge](https://mahjongsoulbadge-production.up.railway.app/badge3/Ssawaul)
## 배지 사용법

아래 주소를 GitHub README에 넣고 닉네임을 바꾸면 됩니다.

4인마작 배지:

```markdown
![Mahjong Soul Badge](https://mahjongsoulbadge-production.up.railway.app/badge/<닉네임>)
```

3인마작 배지:

```markdown
![Mahjong Soul 3P Badge](https://mahjongsoulbadge-production.up.railway.app/badge3/<닉네임>)
```

직접 SVG를 받고 싶으면 아래 엔드포인트를 쓰면 됩니다.

| 경로 | 설명 |
|---|---|
| `/api/player/{nickname}/badge.svg` | 4인마작 SVG |
| `/api/player/{nickname}/badge3.svg` | 3인마작 SVG |
| `/badge/{nickname}` | 4인마작 짧은 경로 |
| `/badge3/{nickname}` | 3인마작 짧은 경로 |
| `/api/debug/{nickname}` | 캐시/갱신 상태 확인용 |

## 갱신 방식

- 서버는 배지 요청 시 5분 이상 지난 데이터를 자동으로 다시 동기화하고, 알려진 플레이어 전체는 기본적으로 24시간마다 동기화합니다.
- `SYNC_INTERVAL` 환경 변수를 주면 동기화 주기를 바꿀 수 있습니다. 기본값은 `86400`초입니다.
- GitHub README에서 이미지가 오래 보이는 문제를 줄이려면 URL 뒤에 `?t=숫자` 같은 cache buster를 붙이면 됩니다.

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn server:app --reload
```

브라우저에서 `http://127.0.0.1:8000` 또는 `http://127.0.0.1:8000/docs`로 확인할 수 있습니다.

## Railway 배포 방법

Railway에서는 프로젝트 루트를 `mahjong_soul_badge` 폴더로 잡는 게 가장 단순합니다.

설정값:

- Root Directory: `mahjong_soul_badge`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
- Environment Variables: 보통 필수 없음. 필요하면 `SYNC_INTERVAL=86400` 같은 값만 추가하면 됩니다.

배포 후에는 Railway가 준 도메인을 `YOUR-DOMAIN` 자리에 넣으면 됩니다. 이 프로젝트는 인증 정보가 필요 없어서 별도의 토큰, 비밀번호, 쿠키 설정은 안 해도 됩니다.

참고:

- `data/` 아래 파일은 캐시 성격이라 배포 후 비어 있어도 정상 동작합니다.
- 캐시를 유지하고 싶으면 Railway volume을 붙일 수 있지만, 필수는 아닙니다.
- `Procfile`도 들어 있어서 Heroku 스타일 배포 방식으로도 같은 시작 명령을 쓸 수 있습니다.

## GitHub Actions 캐시 갱신

`.github/workflows/update-badge-cache.yml`은 30분마다 README의 배지 URL 뒤에 timestamp를 붙여 GitHub Camo 캐시를 갱신합니다. Actions 화면에서 수동 실행할 수도 있습니다.

동작시키려면 Repository Secret 두 개를 넣어야 합니다.

| Secret 이름 | 설명 |
|---|---|
| `BADGE_SERVER_URL` | 배포한 서버 주소 |
| `BADGE_NICKNAME` | 캐시 갱신에 사용할 닉네임 |

설정 후 Actions에서 `Update Badge Cache Buster` 워크플로우를 수동 실행해 확인할 수 있습니다.

워크플로는 다음 alt text를 사용하는 Markdown 이미지 URL을 자동으로 찾습니다.

```markdown
![Mahjong Soul Badge](배지 URL)
![Mahjong Soul 3P Badge](3인 배지 URL)
```

다른 저장소에서 사용하려면 이 YML 파일을 해당 저장소의 `.github/workflows/`에 복사하고 같은 Secret 두 개를 설정하면 됩니다.

## 참고

- 이 프로젝트는 amae-koromo 공개 API를 사용합니다.
- 로그인 없이 동작하지만, amae-koromo가 제공하지 않는 데이터는 표시할 수 없습니다.
- 코드나 배지 형태에 문제가 있으면 이슈로 남겨주세요.
