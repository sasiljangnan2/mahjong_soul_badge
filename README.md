# Mahjong Soul Badge

작혼 전적을 GitHub 프로필에 달 수 있는 SVG 배지로 만들어 줍니다. 전적 데이터는 amae-koromo API에서 가져옵니다.

![Mahjong Soul Badge](https://mahjongsoulbadge-production.up.railway.app/badge/Ssawaul)
![Mahjong Soul 3P Badge](https://mahjongsoulbadge-production.up.railway.app/badge3/Ssawaul)

## 등급별 배지 디자인

<table>
  <tr>
    <td align="center"><b>초심</b><br><img src="https://mahjongsoulbadge-production.up.railway.app/preview/novice.svg" width="360"></td>
    <td align="center"><b>작사</b><br><img src="https://mahjongsoulbadge-production.up.railway.app/preview/adept.svg" width="360"></td>
  </tr>
  <tr>
    <td align="center"><b>작걸</b><br><img src="https://mahjongsoulbadge-production.up.railway.app/preview/expert.svg" width="360"></td>
    <td align="center"><b>작호</b><br><img src="https://mahjongsoulbadge-production.up.railway.app/preview/master.svg" width="360"></td>
  </tr>
  <tr>
    <td align="center"><b>작성</b><br><img src="https://mahjongsoulbadge-production.up.railway.app/preview/saint.svg" width="360"></td>
    <td align="center"><b>혼천</b><br><img src="https://mahjongsoulbadge-production.up.railway.app/preview/celestial.svg" width="360"></td>
  </tr>
</table>

## 배지 사용법

`<닉네임>`만 자신의 작혼 닉네임으로 바꾸면 됩니다.

4인마작 배지:

```markdown
![Mahjong Soul Badge](https://mahjongsoulbadge-production.up.railway.app/badge/<닉네임>)
```

3인마작 배지:

```markdown
![Mahjong Soul 3P Badge](https://mahjongsoulbadge-production.up.railway.app/badge3/<닉네임>)
```

사용 가능한 주소는 다음과 같습니다.

| 경로 | 설명 |
|---|---|
| `/api/player/{nickname}/badge.svg` | 4인마작 SVG |
| `/api/player/{nickname}/badge3.svg` | 3인마작 SVG |
| `/badge/{nickname}` | 4인마작 짧은 경로 |
| `/badge3/{nickname}` | 3인마작 짧은 경로 |
| `/api/debug/{nickname}` | 캐시/갱신 상태 확인용 |

## 데이터 갱신

- 마지막 갱신 후 5분이 지나면 다음 배지 요청에서 데이터를 새로 가져옵니다.
- 등록된 플레이어는 기본 24시간마다 한 번씩 갱신합니다. 주기는 `SYNC_INTERVAL`로 바꿀 수 있습니다.
- amae-koromo에서 받은 토큰은 `AMAE_API_TOKEN`에 넣습니다. 값 앞에 `Bearer`를 붙일 필요는 없습니다.
- 요청 속도는 amae-koromo 정책에 맞춰 최대 1 QPS로 제한합니다.
- 최근 대국을 가져오지 못하면 저장된 기록을 유지하고, 기록도 없으면 순위 통계를 표시합니다.
- GitHub 이미지 캐시가 남아 있으면 배지 URL 뒤에 `?t=숫자`를 붙여 주세요.

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn server:app --reload
```

브라우저에서 `http://127.0.0.1:8000` 또는 `http://127.0.0.1:8000/docs`로 확인할 수 있습니다.

## Railway 배포 방법

Railway 설정 예시:

- Root Directory: `mahjong_soul_badge`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
- Environment Variables: `AMAE_API_TOKEN`, 필요하면 `SYNC_INTERVAL=86400`

배포가 끝나면 README의 배지 주소를 자신의 Railway 도메인으로 바꿉니다.

참고:

- `data/`는 캐시 폴더라 처음에 비어 있어도 됩니다.
- 재배포 뒤에도 캐시를 남기려면 Railway Volume을 연결하세요.
- `Procfile`을 사용하는 배포 환경에서도 실행할 수 있습니다.

## GitHub Actions 캐시 갱신

`.github/workflows/update-badge-cache.yml`은 30분마다 배지 URL의 timestamp를 바꿔 GitHub 이미지 캐시를 갱신합니다. Actions 화면에서 직접 실행해도 됩니다.

동작시키려면 Repository Secret 두 개를 넣어야 합니다.

| Secret 이름 | 설명 |
|---|---|
| `BADGE_SERVER_URL` | 배포한 서버 주소 |
| `BADGE_NICKNAME` | 캐시 갱신에 사용할 닉네임 |

워크플로는 아래 형식의 이미지 주소를 찾습니다.

```markdown
![Mahjong Soul Badge](배지 URL)
![Mahjong Soul 3P Badge](3인 배지 URL)
```

다른 저장소에서는 YML 파일을 `.github/workflows/`에 복사하고 같은 Secret을 등록하면 됩니다.

## 참고

- 전적 반영은 amae-koromo의 수집 시점에 따라 늦어질 수 있습니다.
- API에서 제공하지 않는 기록은 배지에도 표시되지 않습니다.
