"""
test_transformer.py
concept_transformer.py 모듈의 이미지 변환 및 4컷 프레임 합성 단체 테스트
"""

import os
from PIL import Image, ImageDraw
from concept_transformer import transform_four_cut, create_4cut_frame

def run_test():
    print("[Test] 더미 이미지 4장 생성 중...")
    dummy_images = []
    colors = [(255, 182, 193), (173, 216, 230), (144, 238, 144), (255, 255, 224)]
    
    for i, color in enumerate(colors):
        img = Image.new("RGB", (400, 500), color)
        d = ImageDraw.Draw(img)
        d.text((150, 230), f"Sample {i+1}", fill=(50, 50, 50))
        dummy_images.append(img)
        
    print("[Test] 5개 필터 스타일 변환 테스트 시작...")
    styles = ["original", "soft_cartoon", "ghibli", "neon_fantasy", "bw_cinema"]
    
    for style in styles:
        print(f"[Test] '{style}' 스타일 변환 및 프레임 합성 테스트 중...")
        transformed = transform_four_cut(dummy_images, style)
        frame = create_4cut_frame(transformed, brand_title=f"AI 4-CUT ({style.upper()})")
        
        output_filename = f"test_frame_{style}.jpg"
        frame.save(output_filename, format="JPEG")
        print(f" -> 성공적으로 저장됨: {output_filename} ({frame.size})")

if __name__ == "__main__":
    run_test()
