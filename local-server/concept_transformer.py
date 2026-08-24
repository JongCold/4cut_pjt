"""
concept_transformer.py
Stable Diffusion v1.5 Img2Img 파이프라인 및 4컷 스트립 프레임 합성 모듈
"""

import os
import io
import time
from typing import List, Optional
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps

# Diffusers / PyTorch 지연 로딩 및 로컬 Fallback 관리
SD_PIPELINE = None
TORCH_AVAILABLE = False

try:
    import torch
    from diffusers import StableDiffusionImg2ImgPipeline
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


PROMPT_MAPPING = {
    "original": {
        "positive": "high quality photo, portrait, natural warm lighting, sharp focus, masterpiece, 8k uhd, clean skin, detailed eyes",
        "negative": "blurry, ugly, distorted, low quality, noise, bad anatomy, extra limbs"
    },
    "soft_cartoon": {
        "positive": "3d animation style, pixar disney character style, cute facial features, soft smooth studio lighting, vibrant colors, masterpiece, 8k",
        "negative": "photorealistic, real photo, dark, creepy, low quality, ugly, distorted, noise"
    },
    "ghibli": {
        "positive": "studio ghibli anime style, beautiful hand drawn anime illustration, soft watercolor background, warm pastel tones, hayao miyazaki art, highly detailed",
        "negative": "3d render, photorealistic, real photo, dark, low resolution, ugly, bad proportions"
    },
    "neon_fantasy": {
        "positive": "cyberpunk neon fantasy portrait, vibrant glowing magenta and cyan lights, futuristic aesthetic, dramatic contrast, highly detailed, masterpiece",
        "negative": "dull, monochrome, dark background, washed out, low quality, blurry"
    },
    "bw_cinema": {
        "positive": "black and white film portrait, 35mm noir cinema style, dramatic key shadows, high contrast, monochrome, elegant vintage photo, masterpiece",
        "negative": "color, colorful, oversaturated, blurry, bad lighting, low contrast"
    }
}


def load_sd_pipeline():
    """Stable Diffusion v1.5 모델 지연 로딩 (GPU 사용 가능 시)"""
    global SD_PIPELINE, TORCH_AVAILABLE
    if SD_PIPELINE is not None:
        return SD_PIPELINE

    if not TORCH_AVAILABLE:
        print("[AI Engine] PyTorch / Diffusers 패키지가 설치되지 않았습니다. Fallback 엔진을 적용합니다.")
        return None

    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[AI Engine] Stable Diffusion v1.5 로딩 중... (Device: {device})")
        model_id = "runwayml/stable-diffusion-v1-5"
        
        dtype = torch.float16 if device == "cuda" else torch.float32
        pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
            model_id,
            torch_dtype=dtype,
            safety_checker=None
        )
        pipe = pipe.to(device)
        if device == "cuda":
            pipe.enable_attention_slicing()
        SD_PIPELINE = pipe
        print("[AI Engine] Stable Diffusion v1.5 모델 로딩 완료!")
        return SD_PIPELINE
    except Exception as e:
        print(f"[AI Engine] SD 모델 로딩 실패 ({e}). Fallback 엔진으로 전환합니다.")
        return None


def apply_style_fallback(image: Image.Image, style: str) -> Image.Image:
    """GPU / PyTorch 미지원 환경을 위한 고품질 이미지 스타일링 Fallback"""
    img = image.convert("RGB")
    
    if style == "soft_cartoon":
        # 뽀샤시 + 채도 증가 + 콘트라스트 조율 (3D 카툰 흉내)
        img = ImageEnhance.Color(img).enhance(1.4)
        img = ImageEnhance.Contrast(img).enhance(1.1)
        img = img.filter(ImageFilter.SMOOTH_MORE)
        img = ImageEnhance.Sharpness(img).enhance(1.3)
        
    elif style == "ghibli":
        # 수채화 따뜻한 톤 + 가벼운 포스터라이즈
        img = ImageEnhance.Color(img).enhance(1.3)
        img = ImageEnhance.Brightness(img).enhance(1.08)
        # 따뜻한 옐로우/오렌지 틴트 적용
        r, g, b = img.split()
        r = r.point(lambda i: min(255, int(i * 1.05)))
        g = g.point(lambda i: min(255, int(i * 1.02)))
        img = Image.merge("RGB", (r, g, b))
        img = img.filter(ImageFilter.SMOOTH)
        
    elif style == "neon_fantasy":
        # 네온 판타지: 강한 명암 + 시안/마젠타 틴트
        img = ImageEnhance.Contrast(img).enhance(1.35)
        r, g, b = img.split()
        r = r.point(lambda i: min(255, int(i * 1.2)))
        b = b.point(lambda i: min(255, int(i * 1.25)))
        img = Image.merge("RGB", (r, g, b))
        img = ImageEnhance.Color(img).enhance(1.5)
        
    elif style == "bw_cinema":
        # 흑백 시네마: 그레이스케일 + 고콘트라스트
        img = ImageOps.grayscale(img).convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(1.4)
        img = ImageEnhance.Sharpness(img).enhance(1.2)
        
    else:  # original
        # 샤픈 & 선명도 보정
        img = ImageEnhance.Sharpness(img).enhance(1.4)
        img = ImageEnhance.Contrast(img).enhance(1.05)

    return img


def transform_single_image(image: Image.Image, style: str) -> Image.Image:
    """단일 이미지 AI 변환 (SD 1.5 Img2Img 또는 Fallback)"""
    pipe = load_sd_pipeline()
    prompts = PROMPT_MAPPING.get(style, PROMPT_MAPPING["original"])
    
    if pipe is not None:
        try:
            # 타겟 크기 리사이즈 (512x640)
            init_img = image.convert("RGB").resize((512, 640), Image.Resampling.LANCZOS)
            res = pipe(
                prompt=prompts["positive"],
                negative_prompt=prompts["negative"],
                image=init_img,
                strength=0.60,
                guidance_scale=7.5,
                num_inference_steps=20
            ).images[0]
            return res
        except Exception as e:
            print(f"[AI Transform Error] SD 변환 중 오류 발생: {e}. Fallback 적용.")
            return apply_style_fallback(image, style)
    else:
        return apply_style_fallback(image, style)


def transform_four_cut(images: List[Image.Image], style: str) -> List[Image.Image]:
    """4장 이미지 일괄 AI 스타일 변환"""
    transformed = []
    for idx, img in enumerate(images):
        print(f"[AI Process] ({idx+1}/4) 이미지 '{style}' 스타일 변환 중...")
        res = transform_single_image(img, style)
        transformed.append(res)
    return transformed


def create_4cut_frame(images: List[Image.Image], brand_title: str = "AI 4-CUT STUDIO") -> Image.Image:
    """
    3:4 비율 (가로 900px, 세로 1200px) 인생네컷 프레임 합성
    2x2 그리드, 여백, 라운드 슬롯, 하단 브랜드 메타데이터 텍스트
    """
    canvas_w = 900
    canvas_h = 1200
    
    # 캔버스 배경 (흰색)
    frame = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(frame)
    
    # 여백 및 슬롯 배치 계산
    top_margin = int(canvas_h * 0.04)     # 48px
    side_margin = int(canvas_w * 0.06)    # 54px
    bottom_margin = int(canvas_h * 0.13)  # 156px
    gap = int(canvas_w * 0.02)            # 18px
    
    grid_w = canvas_w - (side_margin * 2) - gap  # 774px -> 개별 슬롯 너비 387px
    grid_h = canvas_h - top_margin - bottom_margin - gap  # 978px -> 개별 슬롯 높이 489px
    
    slot_w = grid_w // 2
    slot_h = grid_h // 2
    
    # 4장의 이미지를 2x2 그리드로 배치
    positions = [
        (side_margin, top_margin),
        (side_margin + slot_w + gap, top_margin),
        (side_margin, top_margin + slot_h + gap),
        (side_margin + slot_w + gap, top_margin + slot_h + gap)
    ]
    
    for i in range(min(4, len(images))):
        img = images[i].convert("RGB")
        # 4:5 비율 덮기 (Center Crop)
        img_cropped = ImageOps.fit(img, (slot_w, slot_h), Image.Resampling.LANCZOS)
        
        # 슬롯 테두리 살짝 곡선 모서리 처리 마스크 생성
        mask = Image.new("L", (slot_w, slot_h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, slot_w, slot_h], radius=12, fill=255)
        
        # 캔버스에 안착
        x, y = positions[i]
        frame.paste(img_cropped, (x, y), mask)
        
        # 슬롯 경계 테두리선
        draw.rounded_rectangle([x, y, x + slot_w, y + slot_h], radius=12, outline=(226, 232, 240), width=2)
    
    # 하단 브랜딩 로고 & 날짜 텍스트 삽입
    date_str = datetime.now().strftime("%Y.%m.%d")
    brand_line = f"{brand_title}  •  {date_str}"
    
    try:
        # 기본 폰트 로드 시도
        font = ImageFont.truetype("arial.ttf", 30)
    except IOError:
        font = ImageFont.load_default()
        
    bbox = draw.textbbox((0, 0), brand_line, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    text_x = (canvas_w - text_w) // 2
    text_y = canvas_h - (bottom_margin // 2) - (text_h // 2) - 10
    
    draw.text((text_x, text_y), brand_line, fill=(148, 163, 184), font=font)
    
    return frame
