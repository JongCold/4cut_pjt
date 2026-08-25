"""
concept_transformer.py
High-Performance AI Model & Img2Img Transformation Module for RTX GPUs (8GB VRAM)
DreamShaper v8 & Realistic Vision v5.1 기반 인물 얼굴 고스트/겹침 방지 및 1인 단일 인물 보존 모듈
"""

import os
import io
import time
from typing import List, Optional, Dict
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps

# Diffusers / PyTorch 지연 로딩 및 파이프라인 캐시 관리
PIPELINES_CACHE: Dict[str, any] = {}
TORCH_AVAILABLE = False

try:
    import torch
    from diffusers import StableDiffusionImg2ImgPipeline
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


# 8GB VRAM (RTX 5060/4060 등) 최적화 고성능 모델 레지스트리
MODEL_REGISTRY = {
    "dreamshaper": {
        "name": "DreamShaper v8 (아트/3D카툰/지브리 추천)",
        "model_id": "Lykon/dreamshaper-8",
        "fallback_id": "runwayml/stable-diffusion-v1-5"
    },
    "realistic": {
        "name": "Realistic Vision v5.1 (실사/사진보존/시네마 추천)",
        "model_id": "SG161222/Realistic_Vision_V5.1_noVAE",
        "fallback_id": "runwayml/stable-diffusion-v1-5"
    },
    "sd15": {
        "name": "Stable Diffusion v1.5 (기본 모델)",
        "model_id": "runwayml/stable-diffusion-v1-5",
        "fallback_id": "runwayml/stable-diffusion-v1-5"
    }
}


# 공통 강력한 얼굴 겹침/고스트/다중 인물 방지 네거티브 프롬프트
STRICT_NEGATIVE_PROMPT = (
    "multiple faces, double face, extra face, ghosting, overlapping faces, female face overlay, "
    "extra eyes, deformed iris, distorted eyes, bad face, deformed face, mutated face, "
    "ugly, blurry, extra limbs, bad anatomy, low resolution, noise, artifacts, distorted features"
)


# 스타일 필터별 최적 모델, 프롬프트, Strength 파라미터 매핑
STYLE_CONFIGS = {
    "original": {
        "model_type": "realistic",
        "strength": 0.25,
        "guidance_scale": 7.0,
        "positive": "masterpiece, 8k uhd, ultra-realistic portrait photo of the single person, crystal clear skin texture, sharp detailed eyes, natural studio lighting, photorealistic, 8k",
        "negative": STRICT_NEGATIVE_PROMPT
    },
    "soft_cartoon": {
        "model_type": "dreamshaper",
        "strength": 0.32,
        "guidance_scale": 7.5,
        "positive": "3d pixar disney animation style portrait of the single person, high quality 3d character rendering, cute male facial features, smooth skin shading, vibrant warm colors, sharp detailed eyes, masterpiece",
        "negative": STRICT_NEGATIVE_PROMPT + ", female, girl, woman"
    },
    "ghibli": {
        "model_type": "dreamshaper",
        "strength": 0.32,
        "guidance_scale": 7.5,
        "positive": "studio ghibli anime portrait of the single person, hand drawn anime illustration style, soft watercolor textures, warm anime lighting, detailed male facial features, masterpiece",
        "negative": STRICT_NEGATIVE_PROMPT + ", female, girl, woman"
    },
    "neon_fantasy": {
        "model_type": "realistic",
        "strength": 0.30,
        "guidance_scale": 7.5,
        "positive": "cyberpunk neon fantasy portrait of the single person, glowing cyan and magenta rim light, futuristic cinematic lighting, sharp detailed face, crystal clear eyes, masterpiece",
        "negative": STRICT_NEGATIVE_PROMPT
    },
    "bw_cinema": {
        "model_type": "realistic",
        "strength": 0.28,
        "guidance_scale": 7.0,
        "positive": "black and white 35mm film noir portrait of the single person, elegant studio shadows, high contrast monochrome, sharp focus on eyes and face, masterpiece",
        "negative": STRICT_NEGATIVE_PROMPT
    }
}


def get_sd_pipeline(model_key: str = "dreamshaper"):
    """
    8GB VRAM GPU 최적화 모델 파이프라인 캐싱 및 로딩
    DreamShaper v8 / Realistic Vision v5.1 / SD 1.5 지원
    """
    global PIPELINES_CACHE, TORCH_AVAILABLE
    
    if not TORCH_AVAILABLE:
        print("[AI Engine] PyTorch / Diffusers 미설치. Fallback 엔진을 적용합니다.")
        return None

    if model_key in PIPELINES_CACHE and PIPELINES_CACHE[model_key] is not None:
        return PIPELINES_CACHE[model_key]

    target_cfg = MODEL_REGISTRY.get(model_key, MODEL_REGISTRY["dreamshaper"])
    primary_id = target_cfg["model_id"]
    fallback_id = target_cfg["fallback_id"]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    try_models = [primary_id, fallback_id]
    
    for model_id in try_models:
        try:
            print(f"[AI Engine] 고성능 모델 로딩 시도: '{model_id}' (Device: {device}, FP16)...")
            pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                model_id,
                torch_dtype=dtype,
                safety_checker=None
            )
            pipe = pipe.to(device)
            
            if device == "cuda":
                pipe.enable_attention_slicing()
                
            PIPELINES_CACHE[model_key] = pipe
            print(f"[AI Engine] ✅ 모델 '{model_id}' 로딩 완료!")
            return pipe
        except Exception as e:
            print(f"[AI Engine] ⚠️ 모델 '{model_id}' 로딩 실패 ({e}). 다음 파이프라인 전환 시도...")

    PIPELINES_CACHE[model_key] = None
    return None


def apply_style_fallback(image: Image.Image, style: str) -> Image.Image:
    """GPU / PyTorch 미지원 또는 백엔드 예외 시 인물 보존 고품질 스타일링 Fallback"""
    img = image.convert("RGB")
    
    if style == "soft_cartoon":
        smooth = img.filter(ImageFilter.SMOOTH_MORE)
        enhanced_color = ImageEnhance.Color(smooth).enhance(1.35)
        enhanced_contrast = ImageEnhance.Contrast(enhanced_color).enhance(1.15)
        img = ImageEnhance.Sharpness(enhanced_contrast).enhance(1.3)
        
    elif style == "ghibli":
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
        img = ImageEnhance.Contrast(img).enhance(1.3)
        r, g, b = img.split()
        r = r.point(lambda i: min(255, int(i * 1.22)))
        b = b.point(lambda i: min(255, int(i * 1.28)))
        g = g.point(lambda i: int(i * 0.92))
        img = Image.merge("RGB", (r, g, b))
        img = ImageEnhance.Color(img).enhance(1.4)
        img = ImageEnhance.Sharpness(img).enhance(1.2)
        
    elif style == "bw_cinema":
        img = ImageOps.grayscale(img).convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(1.35)
        img = ImageEnhance.Sharpness(img).enhance(1.25)
        
    else:  # original
        img = ImageEnhance.Sharpness(img).enhance(1.3)
        img = ImageEnhance.Contrast(img).enhance(1.05)

    return img


def transform_single_image(image: Image.Image, style: str) -> Image.Image:
    """
    단일 이미지 AI 변환 (고스트/얼굴 겹침 현상 완전히 제거된 깨끗한 1인 스타일 변환)
    """
    if style == "original":
        return apply_style_fallback(image, "original")

    cfg = STYLE_CONFIGS.get(style, STYLE_CONFIGS["soft_cartoon"])
    model_type = cfg["model_type"]
    
    pipe = get_sd_pipeline(model_type)
    
    if pipe is not None:
        try:
            # 768x960 고해상도 리사이즈
            init_img = image.convert("RGB").resize((768, 960), Image.Resampling.LANCZOS)
            
            # AI 스타일 변환 실행 (중복 얼굴 생성 방지를 위해 strength=0.30~0.32로 정밀 제어)
            res = pipe(
                prompt=cfg["positive"],
                negative_prompt=cfg["negative"],
                image=init_img,
                strength=cfg["strength"],
                guidance_scale=cfg["guidance_scale"],
                num_inference_steps=22
            ).images[0]
            
            # 주의: 전체 캔버스 Image.blend()는 두 얼굴이 반투명하게 겹치는 잔상(고스트)을 유발하므로 
            # AI 변환 결과물(res)을 단일 이미지로 직접 반환하여 깨끗한 1인 인물 이미지를 보장함.
            return res
        except Exception as e:
            print(f"[AI Transform Error] SD 변환 중 오류 ({e}). Fallback 엔진으로 전환.")
            return apply_style_fallback(image, style)
    else:
        return apply_style_fallback(image, style)


def transform_four_cut(images: List[Image.Image], style: str) -> List[Image.Image]:
    """4장 이미지 일괄 AI 스타일 변환"""
    transformed = []
    for idx, img in enumerate(images):
        print(f"[AI Process] ({idx+1}/4) 이미지 '{style}' 고성능 AI 스타일 변환 진행 중...")
        res = transform_single_image(img, style)
        transformed.append(res)
    return transformed


def create_4cut_frame(images: List[Image.Image], brand_title: str = "AI 4-CUT STUDIO") -> Image.Image:
    """
    3:4 비율 (가로 900px, 세로 1200px) 인생네컷 프레임 합성
    """
    canvas_w = 900
    canvas_h = 1200
    
    frame = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(frame)
    
    top_margin = int(canvas_h * 0.04)     # 48px
    side_margin = int(canvas_w * 0.06)    # 54px
    bottom_margin = int(canvas_h * 0.13)  # 156px
    gap = int(canvas_w * 0.02)            # 18px
    
    grid_w = canvas_w - (side_margin * 2) - gap
    grid_h = canvas_h - top_margin - bottom_margin - gap
    
    slot_w = grid_w // 2
    slot_h = grid_h // 2
    
    positions = [
        (side_margin, top_margin),
        (side_margin + slot_w + gap, top_margin),
        (side_margin, top_margin + slot_h + gap),
        (side_margin + slot_w + gap, top_margin + slot_h + gap)
    ]
    
    for idx, img in enumerate(images[:4]):
        img_resized = img.convert("RGB").resize((slot_w, slot_h), Image.Resampling.LANCZOS)
        pos = positions[idx]
        frame.paste(img_resized, pos)
        
        draw.rectangle(
            [pos[0], pos[1], pos[0] + slot_w, pos[1] + slot_h],
            outline=(220, 225, 230),
            width=2
        )
        
    brand_font = None
    sub_font = None
    try:
        font_path = "C:/Windows/Fonts/malgun.ttf"
        if os.path.exists(font_path):
            brand_font = ImageFont.truetype(font_path, 28)
            sub_font = ImageFont.truetype(font_path, 16)
        else:
            brand_font = ImageFont.load_default()
            sub_font = ImageFont.load_default()
    except Exception:
        brand_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
        
    bottom_center_x = canvas_w // 2
    text_y1 = canvas_h - int(bottom_margin * 0.72)
    text_y2 = canvas_h - int(bottom_margin * 0.35)
    
    draw.text((bottom_center_x, text_y1), brand_title, fill=(30, 40, 55), font=brand_font, anchor="mm")
    
    now_str = datetime.now().strftime("%Y.%m.%d | %H:%M")
    draw.text((bottom_center_x, text_y2), f"MEMORY PHOTO • {now_str}", fill=(120, 130, 145), font=sub_font, anchor="mm")
    
    return frame
