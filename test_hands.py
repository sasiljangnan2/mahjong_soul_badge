import json
data = json.load(open('data/players/123883199.json', encoding='utf-8'))
favorite = data['summary']['account'].get('favorite_hu', [])
print('총 favorite_hu 개수:', len(favorite))
for i, fav in enumerate(favorite[:3]):
    hands = fav.get('hands', [])
    print(f'{i+1}번째: type={fav.get("type")}, category={fav.get("category")}, 손패개수={len(hands)}')
    if hands:
        print(f'  hands: {hands}')
