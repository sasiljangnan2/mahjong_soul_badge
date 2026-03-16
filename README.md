# Mahjong Soul Badge

> 작혼 전적을 GitHub README에 배지로 표시해주는 프로젝트입니다.

[![badge preview](https://mahjong-soul-badge.onrender.com/badge/127512551?t=1773646086)](https://mahjong-soul-badge.onrender.com/badge/127512551?t=1773646086)
[![badge preview](https://mahjong-soul-badge.onrender.com/badge3/127512551?t=1773646086)](https://mahjong-soul-badge.onrender.com/badge3/127512551?t=1773646086)
---

## 배지 사용 방법

아래 코드를 `README.md`에 붙여넣고 <작혼_UID>을 교체하세요.

**4인마작 배지:**
```markdown
![Mahjong Soul Badge](https://mahjong-soul-badge.onrender.com/badge/<작혼_UID>?v=2)
```


**3인마작 배지:**
```markdown
![Mahjong Soul 3P Badge](https://mahjong-soul-badge.onrender.com/badge3/<작혼_UID>)
```

---

### 데이터 갱신

- 배지 데이터는 서버에서 **1시간마다 자동으로 갱신**됩니다.

```
https://mahjong-soul-badge.onrender.com/badge/<작혼_UID>?refresh=1
```

> `?refresh=1`은 작혼 서버에 직접 요청하므로 응답이 느릴 수 있습니다.

---

### GitHub Camo 캐시 문제

GitHub README에 이미지를 임베드하면 GitHub의 Camo 프록시를 통해 제공됩니다.  
Camo는 이미지를 자체적으로 캐시하기 때문에 서버 데이터가 갱신되어도 **README에서는 이전 배지가 보일 수 있습니다.**

이를 해결하기 위해 `.github/workflows/update-badge-cache.yml` 워크플로우가 포함되어 있습니다.

- **매시간 자동 실행**하여 서버의 최신 갱신 시각을 URL에 반영합니다.
- URL이 바뀌면 Camo가 새 이미지로 인식해 최신 배지를 표시합니다.
- 사람이 아무것도 하지 않아도 자동으로 동작합니다.

수동으로 즉시 캐시를 깨고 싶다면 README 배지 URL의 `?t=숫자` 값을 임의로 바꾼 뒤 커밋하면 됩니다.

---

### 워크플로우 초기 설정 방법

이 저장소를 포크하거나 직접 배포할 경우, GitHub Actions 워크플로우가 동작하려면 **Repository Secret** 두 개를 설정해야 합니다.

**설정 위치:** `GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret`

| Secret 이름 | 설명 | 예시 |
|---|---|---|
| `BADGE_SERVER_URL` | 배포한 서버의 주소 | `https://mahjong-soul-badge.onrender.com` |
| `BADGE_NICKNAME` | 조회할 작혼 닉네임 | `Ssawaul` |

설정 후 `Actions 탭 → Update Badge Cache Buster → Run workflow`로 수동 실행해 정상 작동을 확인할 수 있습니다.

> **서버를 다른 플랫폼으로 이전할 경우** `BADGE_SERVER_URL` 값만 새 주소로 바꾸면 됩니다. 코드 수정은 필요 없습니다.

---

## 주의사항

- 이 프로젝트는 [PyMajSoul](https://github.com/chaserhkj/PyMajSoul/)을 기반으로 합니다.
- 비공식 프로젝트이며 Catfood Studio / YoStar와 무관합니다.
- 작혼 공식 API가 아닌 비공개 프로토콜을 사용합니다. 문제가 발생할 시 이 리포지토리를 삭제하겠습니다.
- 저작권 문의는 이슈로 남겨주세요.
- 이 개발자는 캐릭터가 이치히메 밖에 없어서 이치히메 프로필로만 적용이 가능합니다. 적용하고 싶은 캐릭터와 왼쪽 위에 뜨는 코드를 이슈로 남겨주시면 추후 추가하겠습니다.
