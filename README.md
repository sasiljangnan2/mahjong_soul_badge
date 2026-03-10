# Mahjong Soul Badge

> 작혼 전적을 GitHub README에 배지로 표시해주는 프로젝트입니다.

[![badge preview](https://mahjong-soul-api.onrender.com/badge/127512551)](https://mahjong-soul-api.onrender.com/badge/127512551)
[![badge preview](https://mahjong-soul-api.onrender.com/badge/badge3/127512551)](https://mahjong-soul-api.onrender.com/badge/badge3/127512551)
---

## 배지 사용 방법

아래 코드를 `README.md`에 붙여넣고 <작혼_UID>`을 교체하세요.

**4인마작 배지:**
```markdown
![Mahjong Soul Badge](https://mahjong-soul-api.onrender.com/badge/<작혼_UID>)
```


**3인마작 배지:**
```markdown
![Mahjong Soul 3P Badge](https://https://mahjong-soul-api.onrender.com/badge/badge3/<작혼_UID>)
```

---

### 데이터 갱신

- 배지 데이터는 서버에서 **1시간마다 자동으로 갱신**됩니다.

```
https://<서버_주소>/badge/<작혼_UID>?refresh=1
```

> `?refresh=1`은 작혼 서버에 직접 요청하므로 응답이 느릴 수 있습니다.

---

## 주의사항

- 이 프로젝트는 [PyMajSoul](https://github.com/chaserhkj/PyMajSoul/)을 기반으로 합니다.
- 비공식 프로젝트이며 Catfood Studio / YoStar와 무관합니다.
- 작혼 공식 API가 아닌 비공개 프로토콜을 사용합니다. 문제가 발생할 시 이 리포지토리를 삭제하겠습니다.
- 저작권 문의는 이슈로 남겨주세요.
- 이 저자는 케릭터가 이치히메 밖에 없어서 이치히메 프로필로만 적용이 가능힙니다. 케릭터와 왼쪽 위에 뜨는 코드를 이슈로 남겨주시면 추후 추가하겠습니다.
