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
        "positive": "masterpiece, 8k uhd, crystal clear portrait photo, natural soft studio lighting, sharp focus, clean skin, detailed eyes, photorealistic, same person",
        "negative": "blurry, ugly, distorted, low quality, noise, bad anatomy, deformed eyes"
    },
    "soft_cartoon": {
        "positive": "3d pixar disney animation style portrait of the exact same person, stylized artistic painting over photo, recognizable facial features, soft smooth character shading, vibrant warm colors, masterpiece, 8k",
        "negative": "deformed face, changed identity, altered face structure, ugly, distorted eyes, dark, blurry, noise"
    },
    "ghibli": {
        "positive": "studio ghibli watercolor animation portrait of the exact same person, beautiful hand drawn anime illustration, soft watercolor texture on portrait, warm pastel aesthetic, hayao miyazaki art style, highly detailed",
        "negative": "deformed face, changed identity, altered face structure, 3d render, distorted anatomy, dark, ugly"
    },
    "neon_fantasy": {
        "positive": "cyberpunk neon fantasy portrait of the exact same person, vibrant glowing magenta and cyan rim light on face, cinematic lighting, futuristic aesthetic, sharp detailed face, masterpiece",
        "negative": "deformed face, changed identity, dark dull, washed out, blurry, low quality"
    },
    "bw_cinema": {
        "positive": "black and white 35mm film portrait of the exact same person, classic noir cinema aesthetic, elegant shadows, high contrast monochrome, sharp focus, masterpiece",
        "negative": "color, colorful, deformed face, changed identity, blurry, bad anatomy"
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
    """GPU / PyTorch 미지원 환경을 위한 인물 보존 고품질 이미지 스타일링 Fallback"""
    img = image.convert("RGB")
    
    if style == "soft_cartoon":
        # 3D 카툰: 부드러운 피부 톤 + 화사한 하이라이트 + 선명한 이목구비
        smooth = img.filter(ImageFilter.SMOOTH_MORE)
        enhanced_color = ImageEnhance.Color(smooth).enhance(1.35)
        enhanced_contrast = ImageEnhance.Contrast(enhanced_color).enhance(1.15)
        img = ImageEnhance.Sharpness(enhanced_contrast).enhance(1.3)
        
    elif style == "ghibli":
        # 지브리: 따뜻한 수채화 톤 + 자연스러운 파스텔 색감
        img = ImageEnhance.Color(img).enhance(1.25)
        img = ImageEnhance.Brightness(img).enhance(1.06)
        r, g, b = img.split()
        r = r.point(lambda i: min(255, int(i * 1.06)))
        g = g.point(lambda i: min(255, int(i * 1.03)))
        b = b.point(lambda i: max(0, int(i * 0.96)))
        img = Image.merge("RGB", (r, g, b))
        img = img.filter(ImageFilter.SMOOTH)
        img = ImageEnhance.Contrast(img).enhance(1.08)
        
    elif style == "neon_fantasy":
        # 네온 판타지: 사이버펑크 틴트 + 드라마틱 글로우
        img = ImageEnhance.Contrast(img).enhance(1.3)
        r, g, b = img.split()
        r = r.point(lambda i: min(255, int(i * 1.22)))
        b = b.point(lambda i: min(255, int(i * 1.28)))
        g = g.point(lambda i: int(i * 0.92))
        img = Image.merge("RGB", (r, g, b))
        img = ImageEnhance.Color(img).enhance(1.4)
        img = ImageEnhance.Sharpness(img).enhance(1.2)
        
    elif style == "bw_cinema":
        # 흑백 시네마: 필름 누아르 흑백 + 깊은 명암비
        img = ImageOps.grayscale(img).convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(1.35)
        img = ImageEnhance.Sharpness(img).enhance(1.25)
        
    else:  # original
        img = ImageEnhance.Sharpness(img).enhance(1.3)
        img = ImageEnhance.Contrast(img).enhance(1.05)

    return img


def transform_single_image(image: Image.Image, style: str) -> Image.Image:
    """단일 이미지 AI 변환 (인물 얼굴 특징 및 구도 100% 보존 파이프라인)"""
    if style == "original":
        return apply_style_fallback(image, "original")

    pipe = load_sd_pipeline()
    prompts = PROMPT_MAPPING.get(style, PROMPT_MAPPING["original"])
    
    if pipe is not None:
        try:
            # 원본 이미지 비율 유지 리사이즈 (512x640)
            init_img = image.convert("RGB").resize((512, 640), Image.Resampling.LANCZOS)
            
            # 인물 얼굴 특징 보존을 위해 strength를 0.38로 최적화
            res = pipe(
                prompt=prompts["positive"],
                negative_prompt=prompts["negative"],
                image=init_img,
                strength=0.38,
                guidance_scale=7.5,
                num_inference_steps=20
            ).images[0]
            
            # 원본 윤곽/이목구비의 정밀도를 유지하기 위해 미세 블렌딩 (85% AI 스타일 + 15% 원본 디테일)
            blended = Image.blend(init_img, res, alpha=0.85)
            return blended
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
