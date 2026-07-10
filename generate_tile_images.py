#!/usr/bin/env python3
"""마작 타일 이미지 자동 생성 스크립트 (새로운 디자인)"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math
import os
import math

# 타일 이미지 저장 디렉토리
TILES_DIR = Path(__file__).resolve().parent / "assets" / "tiles"
TILES_DIR.mkdir(parents=True, exist_ok=True)

# 타일 설정
TILE_WIDTH = 80
TILE_HEIGHT = 112

def get_font(size, cjk=False):
    """폰트 로드 (한자/한글 지원)"""
    font_names = [
        "malgun.ttf",      # 맑은 고딕 (Windows 한글)
        "meiryo.ttf",      # Meiryo (Windows 일본어)
        "simsun.ttc",      # SimSun (Windows 중문)
        "arial.ttf",       # Arial (폴백)
    ]
    
    font_dirs = ["C:\\Windows\\Fonts"]
    
    for font_dir in font_dirs:
        if os.path.exists(font_dir):
            for font_name in font_names:
                font_path = os.path.join(font_dir, font_name)
                if os.path.exists(font_path):
                    try:
                        return ImageFont.truetype(font_path, size)
                    except Exception:
                        pass
    
    return ImageFont.load_default()

def create_rounded_mask(width, height, radius=3):
    """둥근 모서리 마스크 생성"""
    mask = Image.new('L', (width, height), 255)
    mask_draw = ImageDraw.Draw(mask)
    
    # 네 모서리에 원형 마스크 적용
    # 좌상단
    mask_draw.pieslice([(0, 0), (radius*2, radius*2)],
                       180, 270, fill=0)
    # 우상단
    mask_draw.pieslice([(width-radius*2, 0), (width, radius*2)],
                       270, 360, fill=0)
    # 좌하단
    mask_draw.pieslice([(0, height-radius*2), (radius*2, height)],
                       90, 180, fill=0)
    # 우하단
    mask_draw.pieslice([(width-radius*2, height-radius*2), (width, height)],
                       0, 90, fill=0)
    
    return mask

def create_tile(num, suit, is_red=False):
    """마작 타일 이미지 생성 (새로운 디자인)
    
    Args:
        num: 숫자 (1-9)
        suit: 종류 ('m', 'p', 's', 'z')
        is_red: 적도 여부
    """
    # 큰 크기로 먼저 생성 (품질 향상을 위해 5배 크기)
    large_width = TILE_WIDTH * 5
    large_height = TILE_HEIGHT * 5
    
    # RGBA 이미지 생성 (투명 배경)
    img = Image.new('RGBA', (large_width, large_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # 둥근 사각형을 하얀색으로 채우기
    radius = int(6 * 5)  # 5배 크기의 둥근 모서리
    draw.rounded_rectangle(
        [(0, 0), (large_width-1, large_height-1)],
        radius=radius,
        fill=(255, 255, 255, 255),
        outline=(0, 0, 0, 255),
        width=10
    )
    
    # 한자 매핑
    kan_numbers = {
        1: '一', 2: '二', 3: '三', 4: '四', 5: '伍',
        6: '六', 7: '七', 8: '八', 9: '九'
    }
    
    honor_names = {
        1: '東', 2: '南', 3: '西', 4: '北',
        5: '白', 6: '發', 7: '中'
    }
    
    is_red_five = is_red and (num == 5 and suit in ['m', 'p', 's'])
    text_color = (255, 0, 0, 255) if is_red_five else (0, 0, 0, 255)
    
    if suit == 'm':  # 만패: 한자 + 萬
        # 색상 설정
        c_red = (180, 40, 40, 255)    # '萬' 자 색상 (짙은 빨강)
        c_black = (15, 15, 15, 255)   # 숫자 색상 (거의 검정)
        
        # 적도라(Red 5)일 경우 밝은 빨강으로 통일
        if is_red_five:
            c_red = (255, 0, 0, 255)
            c_black = (255, 0, 0, 255)
            
        # 폰트 크기 설정 (안정감을 위해 40%로 설정)
        font_size = int(large_height * 0.40)
        kan_font = get_font(font_size, cjk=True)
        # 글씨 두께 더 두껍게 조정 (0.3 -> 0.8)
        stroke_w = int(0.8 * 5)
        
        # 텍스트 높이 계산하여 수직 중앙 정렬
        kan_text = kan_numbers[num]
        
        # 1. 숫자 높이 측정
        bbox_num = draw.textbbox((0, 0), kan_text, font=kan_font)
        h_num = bbox_num[3] - bbox_num[1]
        
        # 2. '萬' 높이 측정
        bbox_wan = draw.textbbox((0, 0), '萬', font=kan_font)
        h_wan = bbox_wan[3] - bbox_wan[1]
        
        # 3. 간격 및 전체 높이 계산
        gap = int(large_height * 0.02) # 두 글자 사이 간격 (좁게)
        total_h = h_num + gap + h_wan
        
        # 4. 시작 Y 좌표 (상단 여백 = 하단 여백이 되도록)
        start_y = (large_height - total_h) // 2
        
        # 5. 그리기 (anchor='mt' 사용: 상단 기준 위치 잡기)
        # 숫자 (위)
        # textbbox의 y오프셋 보정
        draw.text((large_width // 2, start_y ), kan_text, 
                 fill=c_black, font=kan_font, anchor='mt',
                 stroke_width=stroke_w, stroke_fill=c_black)
        
        # '萬' (아래)
        draw.text((large_width // 2, start_y + h_num + gap), '萬', 
                 fill=c_red, font=kan_font, anchor='mt',
                 stroke_width=stroke_w, stroke_fill=c_red)

    
    elif suit == 'p':  # 통패: 동전 (마작패 배치)
        # 마작패 정규 색상: 파란색 동전 (5p_red는 빨간색)
        # 기본 색상 정의 (마작패 스타일)
        c_blue = (45, 85, 150, 255)   # 짙은 파란색
        c_red = (200, 50, 50, 255)    # 짙은 빨간색
        c_green = (40, 120, 60, 255)  # 짙은 녹색
        
        # 적도라(Red 5)일 경우 모든 색상을 밝은 빨간색으로 통일
        if is_red_five:
            c_blue = c_red = c_green = (255, 0, 0, 255)
        
        # 숫자별 동전 크기 조정 (마작패 비율 반영)
        if num == 1:
            coin_size = int(24 * 5)  # 1통: 매우 큼 (반지름 120)
        elif num <= 2:
            coin_size = int(17 * 5)  # 2~7통: 중간 크기 (반지름 60)
        elif num <= 6:
            coin_size = int(13 * 5)  # 2~7통: 중간 크기 (반지름 60)
        else:
            coin_size = int(12 * 5) # 8~9통: 작음 (반지름 47 - 촘촘하게 배치 시 겹치지 않게)

        # 숫자별 동전 위치 배치
        cx_center = large_width // 2
        cy_center = large_height // 2
        quarter_w = large_width // 4
        quarter_h = large_height // 4
        
        # 간격 미세 조정용 계수 (중앙 집중형 배치를 위함)
        compact_scale = 0.85
        cw = quarter_w * compact_scale # 조금 더 좁게
        ch = quarter_h * compact_scale * 1.2 # 조금 더 좁게

        # 8, 9통의 경우 3열 배치를 위해 기존 quarter_w 유지
        w3 = quarter_w 
        h3 = quarter_h 

        # 각 숫자별 좌표 매핑 (마작패 정규 배치 & 색상 적용)
        # 형식: (x, y, color)
        coin_positions_map = {
            # 1통: 대형 빨간 동전
            1: [(cx_center, cy_center, c_red)],
            
            # 2통: 파란색 2개
            2: [(cx_center, cy_center - ch, c_blue), (cx_center, cy_center + ch, c_blue)],
            
            # 3통: 상단 파랑, 중앙 빨강, 하단 파랑
            3: [(cx_center - cw, cy_center - ch, c_blue), 
                (cx_center, cy_center, c_red), 
                (cx_center + cw, cy_center + ch, c_blue)],
            
            # 4통: 파란색 4개
            4: [(cx_center - cw, cy_center - ch, c_blue), (cx_center + cw, cy_center - ch, c_blue),
                (cx_center - cw, cy_center + ch, c_blue), (cx_center + cw, cy_center + ch, c_blue)],
            
            # 5통: 4통(파랑) + 중앙(빨강)
            5: [(cx_center - cw, cy_center - ch, c_blue), (cx_center + cw, cy_center - ch, c_blue),
                (cx_center, cy_center, c_red),
                (cx_center - cw, cy_center + ch, c_blue), (cx_center + cw, cy_center + ch, c_blue)],
            
            # 6통: 녹색 6개 (상단 녹색, 하단 녹색)
            6: [(cx_center - w3 * 0.55, cy_center - h3 * 1.0, c_green), (cx_center + w3 * 0.55, cy_center - h3 * 1.0, c_green),
                (cx_center - w3 * 0.55, cy_center + h3 * 0.2, c_red), (cx_center + w3 * 0.55, cy_center + h3 * 0.2, c_red),
                (cx_center - w3 * 0.55, cy_center + h3 * 1.0, c_red), (cx_center + w3 * 0.55, cy_center + h3 * 1.0, c_red)],

            # 7통: 상단 3개(녹색, 대각선), 하단 4개(빨강, 사각형)
            # 간격 조정: 더 모여있도록 (compact)
            7: [
                # 상단 3개 (대각선: 좌상 -> 우하) - 녹색
                (cx_center - cw * 1.15 , cy_center - ch * 1.13, c_green),
                (cx_center,             cy_center - ch * 0.85, c_green),
                (cx_center + cw * 1.15, cy_center - ch * 0.57, c_green),
                
                # 하단 4개 (사각형) - 빨강
                (cx_center - w3 * 0.53, cy_center + h3 * 0.22, c_red), (cx_center + w3 * 0.53, cy_center + h3 * 0.22, c_red),
                (cx_center - w3 * 0.53, cy_center + h3 * 1.0, c_red), (cx_center + w3 * 0.53, cy_center + h3 * 1.0, c_red)
            ],
            
            # 8통: 파란색 8개
            # 간격 조정: 더 모여있도록 (compact)
            8: [
                # 좌측 4개 (상하 대칭)
                (cx_center - w3 * 0.55, cy_center - h3 * 1.12, c_blue),
                (cx_center - w3 * 0.55, cy_center - h3 * 0.38, c_blue),
                (cx_center - w3 * 0.55, cy_center + h3 * 0.38, c_blue),
                (cx_center - w3 * 0.55, cy_center + h3 * 1.12, c_blue),
                # 우측 4개
                (cx_center + w3 * 0.55, cy_center - h3 * 1.12, c_blue),
                (cx_center + w3 * 0.55, cy_center - h3 * 0.38, c_blue),
                (cx_center + w3 * 0.55, cy_center + h3 * 0.38, c_blue),
                (cx_center + w3 * 0.55, cy_center + h3 * 1.12, c_blue),
            ],
            
            # 9통: 상단(녹색), 중단(빨강), 하단(녹색)
            9: [(cx_center - w3, cy_center - h3, c_green), (cx_center, cy_center - h3, c_green), (cx_center + w3, cy_center - h3, c_green),
                (cx_center - w3, cy_center, c_red), (cx_center, cy_center, c_red), (cx_center + w3, cy_center, c_red),
                (cx_center - w3, cy_center + h3, c_green), (cx_center, cy_center + h3, c_green), (cx_center + w3, cy_center + h3, c_green)],
        }
        
        positions = coin_positions_map.get(num, [(cx_center, cy_center, c_blue)])
        
        for cx, cy, color in positions:
            # 동전을 단순한 원으로 그리기
            # 통패 내부 테두리 두께 강화: 3 -> 10
            draw.ellipse(
                [(cx-coin_size, cy-coin_size), (cx+coin_size, cy+coin_size)],
                outline=color, width=25, fill=(200, 200, 200, 220)  # 밝은 회색 내부
            )
    
    elif suit == 's':  # 삭패: 대나무
        # 기본 색상
        c_green = (40, 120, 60, 255)  # 짙은 녹색
        c_red = (200, 50, 50, 255)    # 짙은 빨간색
        c_blue = (45, 85, 150, 255)   # 짙은 파란색 (가끔 씀)
        
        # 적도라 처리
        if is_red_five:
            c_green = (255, 0, 0, 255)
            c_red = (255, 0, 0, 255)
            c_blue = (255, 0, 0, 255)

        cx = large_width // 2
        cy = large_height // 2
        qw = large_width // 4
        qh = large_height // 4

        # 대나무 그리기 헬퍼
        def draw_stick(x, y, color, scale=1.0, angle=0):
            # Stick Dimensions (Fuller Look)
            # 기존 10.5 -> 12.5 로 확대 (두께 증가)
            sw = int(12.5 * 5 * scale)   
            sl = int(36 * 5 * scale)
            
            hw = sw / 2
            hl = sl / 2
            # Vertical Rect Points centered at 0,0
            pts = [(-hw, -hl), (hw, -hl), (hw, hl), (-hw, hl)]
            
            # Rotate & Translate
            rad = math.radians(angle)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            
            # Rotate & Translate
            new_pts = []
            for px, py in pts:
                rx = px * cos_a - py * sin_a
                ry = px * sin_a + py * cos_a
                new_pts.append((x + rx, y + ry))
            
            # Stick Body with Outline
            # Determine background fill color based on outline color
            # Default Light Green for Green
            # c_green: (40, 120, 60, 255) -> Light: (210, 240, 210, 255)
            # c_red: (200, 50, 50, 255) -> Light: (250, 210, 210, 255)
            
            if color == c_red or (is_red_five and color == c_green): # Red case
                fill_c = (255, 220, 220, 255)
            else: # Green case
                fill_c = (210, 240, 210, 255)

            draw.polygon(new_pts, fill=fill_c, outline=color, width=18)
            
            # Node (Center line matching border)
            node_h = int(2 * 5 * scale)
            nhl = node_h / 2
            n_pts = [(-hw+3, -nhl), (hw-3, -nhl), (hw-3, nhl), (-hw+3, nhl)] # Slightly narrower than width
            
            final_n_pts = []
            for px, py in n_pts:
                rx = px * cos_a - py * sin_a
                ry = px * sin_a + py * cos_a
                final_n_pts.append((x + rx, y + ry))
                
            draw.polygon(final_n_pts, fill=color, width=20)

        if num == 1:
            # 1삭: 공작새 (단순화된 새 모양)
            bird_color = (200, 50, 50, 255) if is_red_five else c_green
            # 꼬리 (부채꼴) - 상단으로 펼쳐짐
            for angle in range(200, 341, 15):
                rad = math.radians(angle)
                tx = cx + int(math.cos(rad) * qw * 1.8)
                ty = cy + int(math.sin(rad) * qh * 1.5)
                draw.line([(cx, cy + qh//2), (tx, ty)], fill=bird_color, width=15)
                # 꼬리 끝 장식
                draw.ellipse([(tx-10, ty-10), (tx+10, ty+10)], fill=(255,215,0,255))

            # 몸통
            body_h = int(qh * 1.8)
            draw.ellipse([(cx - qw//1.8, cy - qh//2), (cx + qw//1.8, cy + body_h)], fill=bird_color)
            # 머리
            draw.ellipse([(cx - qw//3, cy - qh), (cx + qw//3, cy - qh + qw)], fill=(255, 215, 0, 255))
            # 눈
            draw.ellipse([(cx - 5, cy - qh + 15), (cx + 5, cy - qh + 25)], fill=(0,0,0,255))
            # 1 글자 대신 중앙에 '1' 같은 느낌의 장식? 아니, 그냥 새 모양으로 충분.

        else:
            positions = [] # (x, y, color, angle, scale)
            
            # Common Sizes
            # 2,3,4,5용 (Large Scale) - 간격 더 넓힘
            s_lg = 1
            w3 = qw * 0.65  # 0.58 -> 0.65 (더 넓게)
            h3 = qh * 0.95  # 0.85 -> 0.95 (더 넓게)
            
            # 6,7,9 용 (Medium Scale, Dense) - 간격 더 크게
            s_md = 0.85
            h_dense = 175   # 160 -> 175 (중첩 방지 및 여유 공간 확보)
            
            if num == 2:
                # 2삭: 하나는 위, 하나는 아래
                positions = [
                    (cx, cy - h3, c_green, 0, s_lg),
                    (cx, cy + h3, c_green, 0, s_lg)
                ]
            elif num == 3:
                # 3삭: 상단 1, 하단 2
                positions = [
                    (cx, cy - h3, c_green, 0, s_lg),
                    (cx - w3, cy + h3, c_green, 0, s_lg),
                    (cx + w3, cy + h3, c_green, 0, s_lg)
                ]
            elif num == 4:
                # 4삭: 상단 2, 하단 2
                positions = [
                    (cx - w3, cy - h3, c_green, 0, s_lg), (cx + w3, cy - h3, c_green, 0, s_lg),
                    (cx - w3, cy + h3, c_green, 0, s_lg), (cx + w3, cy + h3, c_green, 0, s_lg)
                ]
            elif num == 5:
                # 5삭: 4삭 + 중앙 1
                cen = c_red if not is_red_five else c_green
                if is_red_five: cen = c_red 
                
                positions = [
                    (cx - w3 -10, cy - h3, c_green, 0, s_lg), (cx + w3 + 10, cy - h3, c_green, 0, s_lg),
                    (cx, cy, cen, 0, s_lg),
                    (cx - w3 - 10, cy + h3, c_green, 0, s_lg), (cx + w3 + 10, cy + h3, c_green, 0, s_lg)
                ]
            elif num == 6:
                # 6삭: 3열 2행 (3x2)
                # 간격 넓힘
                h6 = 105  # 90 -> 105
                w6 = qw
                
                # 상단 3개
                positions = [
                    (cx - w6, cy - h6 * 1.2, c_green, 0, s_lg), 
                    (cx,      cy - h6 * 1.2, c_green, 0, s_lg), 
                    (cx + w6, cy - h6 * 1.2, c_green, 0, s_lg),
                    
                # 하단 3개
                    (cx - w6, cy + h6 * 1.2, c_green, 0, s_lg), 
                    (cx,      cy + h6 * 1.2, c_green, 0, s_lg), 
                    (cx + w6, cy + h6 * 1.2, c_green, 0, s_lg)
                ]
            elif num == 7:
                # 7삭: 1(Top) - 3(Mid) - 3(Bot) (유저 요청: 일반적인 마작패 구성)
                h7 = h_dense # 175
                w7 = qw
                
                # 상단 1개
                positions.append((cx, cy - h7, c_red, 0, s_md))
                
                # 중단 3개
                positions.append((cx - w7, cy, c_green, 0, s_md))
                positions.append((cx,      cy, c_green, 0, s_md))
                positions.append((cx + w7, cy, c_green, 0, s_md))
                
                # 하단 3개
                positions.append((cx - w7, cy + h7, c_green, 0, s_md))
                positions.append((cx,      cy + h7, c_green, 0, s_md))
                positions.append((cx + w7, cy + h7, c_green, 0, s_md))
                
            elif num == 8:
                # 8삭
                s8 = s_md
                t_ang = -20
                t_ang2 = 20
                h8 = 110  # 150 -> 110
                
                # 상단
                positions.append((cx - w3 * 1.5, cy - h8 * 1.2, c_green, 0, s_lg))
                positions.append((cx - w3 * 0.5, cy - h8 * 1.1, c_green, t_ang2, s8))
                positions.append((cx + w3 * 0.5, cy - h8 * 1.1, c_green, t_ang, s8))
                positions.append((cx + w3 * 1.5, cy - h8 * 1.2, c_green, 0, s_lg))
                
                # 하단
                positions.append((cx - w3 * 1.5, cy + h8 * 1.2, c_green,0, s_lg))
                positions.append((cx - w3 * 0.5, cy + h8 * 1.1, c_green, t_ang, s8))
                positions.append((cx + w3 * 0.5, cy + h8 * 1.1, c_green, t_ang2, s8))
                positions.append((cx + w3 * 1.5, cy + h8 * 1.2, c_green, 0, s_lg))
                
            elif num == 9:
                # 9삭: 3열 3행
                h9 = h_dense # 175
                w9 = qw  # 0.7 -> 0.75
                
                # Top
                positions.append((cx - w9, cy - h9, c_green, 0, s_md))
                positions.append((cx,      cy - h9, c_green, 0, s_md))
                positions.append((cx + w9, cy - h9, c_green, 0, s_md))
                
                # Mid
                positions.append((cx - w9, cy, c_red, 0, s_md))
                positions.append((cx,      cy, c_red, 0, s_md))
                positions.append((cx + w9, cy, c_red, 0, s_md))
                
                # Bot
                positions.append((cx - w9, cy + h9, c_green, 0, s_md))
                positions.append((cx,      cy + h9, c_green, 0, s_md))
                positions.append((cx + w9, cy + h9, c_green, 0, s_md))

            for item in positions:
                # 언패킹 유연하게 (scale이 있을수도 없을수도.. 위 코드에선 다 넣음)
                if len(item) == 5:
                    px, py, pcolor, pangle, pscale = item
                else:
                    px, py, pcolor, pangle = item
                    pscale = 1.0
                draw_stick(px, py, pcolor, angle=pangle, scale=pscale)

    
    elif suit == 'z':  # 자패: 한자
        # 색상 설정
        # 동남서북백(검정), 발(녹색), 중(빨강)
        c_black = (15, 15, 15, 255)
        c_green = (40, 120, 60, 255)
        c_red = (200, 50, 50, 255)
        
        color_map = {
            1: c_black, # 동
            2: c_black, # 남
            3: c_black, # 서
            4: c_black, # 북
            5: c_black, # 백
            6: c_green, # 발
            7: c_red    # 중
        }
        
        text_color = color_map.get(num, c_black)
        
        # 5번(백패)은 아무것도 그리지 않음 (빈 타일)
        if num != 5:
            # 폰트 크기: 높이의 60%
            font_size = int(large_height * 0.6)
            font = get_font(font_size, cjk=True)
            text = honor_names.get(num, str(num))
            
            # 완전한 중앙 정렬 (anchor='mm')
            # 두께를 만패와 비슷하게 두껍게 조정 (0.5 * 5 -> 0.8 * 5)
            stroke_w = int(0.8 * 5)
            
            # Y 좌표 보정 없이 정중앙에 배치
            draw.text((large_width // 2, large_height // 2 - 12), text, 
                    fill=text_color, font=font, anchor='mm',
                    stroke_width=stroke_w, stroke_fill=text_color)
    
    # 원래 크기로 축소
    img = img.resize((TILE_WIDTH, TILE_HEIGHT), Image.Resampling.LANCZOS)
    
    return img

def main():
    """모든 마작 타일 이미지 생성"""
    print("마작 타일 이미지 생성 중...")
    
    tiles_list = [
        # 일반 타일
        *[(i, 'm', False) for i in range(1, 10)],
        *[(i, 'p', False) for i in range(1, 10)],
        *[(i, 's', False) for i in range(1, 10)],
        *[(i, 'z', False) for i in range(1, 8)],
        # 적도 5
        (5, 'm', True), (5, 'p', True), (5, 's', True),
    ]
    
    honor_names = {
        1: '東', 2: '南', 3: '西', 4: '北',
        5: '白', 6: '發', 7: '中'
    }
    
    for num, suit, is_red in tiles_list:
        try:
            img = create_tile(num, suit, is_red=is_red)
            
            if is_red and num == 5 and suit in ['m', 'p', 's']:
                filename = f"{num}{suit}_red.png"
            else:
                filename = f"{num}{suit}.png"
            
            filepath = TILES_DIR / filename
            img.save(filepath, "PNG")
            
            if suit == 'z':
                print(f"  ✓ {filename} 생성됨 ({honor_names[num]})")
            else:
                print(f"  ✓ {filename} 생성됨")
        except Exception as e:
            print(f"  ✗ {num}{suit} 생성 실패: {e}")
    
    print(f"\n✓ 총 {len(tiles_list)}개 타일 이미지 생성 완료!")
    print(f"  저장 경로: {TILES_DIR}")

if __name__ == "__main__":
    main()
