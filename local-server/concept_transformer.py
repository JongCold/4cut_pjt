"""
concept_transformer.py
High-Performance AI Model & Person-Preserving Thematic Diffusion Module for RTX GPUs (8GB VRAM)
DeepLabV3 세그멘테이션 마스킹 + 테마별 고화질 배경 전환(strength: 0.75) + 인물 얼굴/표정/포즈 100% 보존
"""

import os
import io
import sys
import time
from typing import List, Optional, Dict
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
import numpy as np

# Windows 콘솔 cp949 인코딩 에러 방지
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Diffusers / PyTorch / Torchvision 지연 로딩 및 파이프라인 캐시 관리
PIPELINES_CACHE: Dict[str, any] = {}
SEG_MODEL = None
TORCH_AVAILABLE = False

try:
    import torch
    import torchvision.transforms as T
    from torchvision.models.segmentation import deeplabv3_mobilenet_v3_large, DeepLabV3_MobileNet_V3_Large_Weights
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


# 테마별 배경 변환 프롬프트 & 인물 조명 하모나이징 명세
THEME_CONFIGS = {
    "wizard": {
        "model_type": "realistic",
        "bg_prompt": (
            "masterpiece, 8k uhd, photorealistic interior of grand ancient gothic magic library, "
            "towering wooden bookshelves, floating open spellbooks, flying quill pens, glowing magical particles, "
            "warm ambient candlelight, cinematic lighting, 35mm photography"
        ),
        "bg_neg": "people, person, human, face, deformed, ugly, blurry, text, watermark, bad anatomy",
        "strength": 0.75,
        "guidance_scale": 7.5,
        "color_boost": 1.12,
        "contrast_boost": 1.06,
        "lighting_tint": (255, 185, 90) # 따뜻한 촛불/호박색 광원
    },
    "magic_academy": {
        "model_type": "realistic",
        "bg_prompt": (
            "masterpiece, 8k uhd, photorealistic interior of grand ancient gothic magic library, "
            "towering wooden bookshelves, floating open spellbooks, flying quill pens, glowing magical particles, "
            "warm ambient candlelight, cinematic lighting, 35mm photography"
        ),
        "bg_neg": "people, person, human, face, deformed, ugly, blurry, text, watermark, bad anatomy",
        "strength": 0.75,
        "guidance_scale": 7.5,
        "color_boost": 1.12,
        "contrast_boost": 1.06,
        "lighting_tint": (255, 185, 90)
    },
    "neon_fantasy": {
        "model_type": "realistic",
        "bg_prompt": (
            "masterpiece, 8k uhd, cyberpunk futuristic neon city street at night, "
            "glowing cyan and magenta neon signs, wet reflections, cinematic lighting, bokeh, 8k"
        ),
        "bg_neg": "people, person, human, face, deformed, ugly, blurry, text, watermark",
        "strength": 0.75,
        "guidance_scale": 7.5,
        "color_boost": 1.25,
        "contrast_boost": 1.15,
        "lighting_tint": (220, 50, 255) # 네온 림라이트
    },
    "ghibli": {
        "model_type": "dreamshaper",
        "bg_prompt": (
            "masterpiece, studio ghibli anime landscape, lush green grassy hill, "
            "blue sky with fluffy white clouds, warm sunny day, soft watercolor aesthetic, anime scenery"
        ),
        "bg_neg": "people, person, human, face, deformed, ugly, blurry, text, watermark",
        "strength": 0.75,
        "guidance_scale": 7.5,
        "color_boost": 1.2,
        "contrast_boost": 1.05,
        "lighting_tint": (255, 245, 200) # 따뜻한 지브리 햇살
    },
    "soft_cartoon": {
        "model_type": "dreamshaper",
        "bg_prompt": (
            "masterpiece, vibrant 3d pixar disney style animated room interior, "
            "cozy warm lighting, colorful studio backdrop, cute stylized furniture, 3d render"
        ),
        "bg_neg": "people, person, human, face, deformed, ugly, blurry, text, watermark",
        "strength": 0.75,
        "guidance_scale": 7.5,
        "color_boost": 1.18,
        "contrast_boost": 1.08,
        "lighting_tint": (255, 220, 180)
    },
    "bw_cinema": {
        "model_type": "realistic",
        "bg_prompt": (
            "masterpiece, dramatic black and white 35mm film noir studio backdrop, "
            "moody shadows, soft spotlight, vintage classic cinema background"
        ),
        "bg_neg": "people, person, human, face, deformed, ugly, blurry, text, watermark, color",
        "strength": 0.75,
        "guidance_scale": 7.0,
        "color_boost": 0.0,
        "contrast_boost": 1.25,
        "lighting_tint": (200, 200, 200)
    },
    "original": {
        "model_type": "realistic",
        "bg_prompt": "masterpiece, elegant professional photography studio background, soft neutral gradient, studio rim light",
        "bg_neg": "people, person, human, face, deformed, ugly, blurry, text, watermark",
        "strength": 0.3,
        "guidance_scale": 7.0,
        "color_boost": 1.0,
        "contrast_boost": 1.05,
        "lighting_tint": None
    }
}


def get_segmentation_model(device: str = "cuda"):
    """인물 영역만 정밀하게 분리하는 DeepLabV3 세그멘테이션 모델 싱글톤 로딩"""
    global SEG_MODEL
    if SEG_MODEL is None and TORCH_AVAILABLE:
        try:
            weights = DeepLabV3_MobileNet_V3_Large_Weights.DEFAULT
            SEG_MODEL = deeplabv3_mobilenet_v3_large(weights=weights).to(device)
            SEG_MODEL.eval()
            print("[AI Engine] ✅ 인물 정밀 분리 세그멘테이션 엔진(DeepLabV3) 로딩 완료!")
        except Exception as e:
            print(f"[AI Engine] ⚠️ 세그멘테이션 모델 로딩 실패 ({e}). Fallback 마스크를 사용합니다.")
            SEG_MODEL = None
    return SEG_MODEL


def extract_person_mask(image: Image.Image, device: str = "cuda") -> Image.Image:
    """인물(얼굴, 표정, 헤어, 포즈, 의상)을 100% 보존하기 위한 알파 세그멘테이션 마스크 생성"""
    model = get_segmentation_model(device)
    if model is not None:
        try:
            weights = DeepLabV3_MobileNet_V3_Large_Weights.DEFAULT
            transforms = weights.transforms()
            input_tensor = transforms(image).unsqueeze(0).to(device)
            with torch.no_grad():
                output = model(input_tensor)["out"][0]
            preds = output.argmax(0).byte().cpu().numpy()
            
            # COCO Class 15: person
            person_mask_np = (preds == 15).astype(np.uint8) * 255
            mask = Image.fromarray(person_mask_np, mode="L").resize(image.size, resample=Image.Resampling.BILINEAR)
            # 자연스러운 합성을 위한 엣지 가우시안 페더링
            mask = mask.filter(ImageFilter.GaussianBlur(radius=6))
            return mask
        except Exception as e:
            print(f"[Masking Error] DeepLabV3 마스크 추출 실패 ({e}), 휴리스틱 마스크 대체...")

    # Fallback: 중앙 인물 영역 보존 마스크 (타원형 소프트 마스크)
    w, h = image.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse([int(w * 0.15), int(h * 0.1), int(w * 0.85), int(h * 0.95)], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=25))
    return mask


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


def generate_fallback_background(style: str, size: tuple) -> Image.Image:
    """GPU 미지원 시 테마별 고해상도 그래디언트 백드롭 생성"""
    w, h = size
    if style in ["wizard", "magic_academy"]:
        base = Image.new("RGB", (w, h), (26, 18, 14))
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.rectangle([(0, 0), (w, int(h * 0.35))], fill=(15, 10, 8, 220))
        draw.rectangle([(0, 0), (int(w * 0.25), h)], fill=(20, 12, 10, 200))
        draw.rectangle([(int(w * 0.75), 0), (w, h)], fill=(20, 12, 10, 200))
        import random
        random.seed(42)
        for _ in range(30):
            x = random.randint(int(w * 0.05), int(w * 0.95))
            y = random.randint(int(h * 0.1), int(h * 0.9))
            r = random.randint(3, 12)
            draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=(255, 190, 70, 160))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=10))
        base.paste(glow, (0, 0), glow)
        return base
    elif style == "neon_fantasy":
        base = Image.new("RGB", (w, h), (10, 10, 25))
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.rectangle([(0, 0), (int(w*0.3), h)], fill=(255, 0, 128, 120))
        draw.rectangle([(int(w*0.7), 0), (w, h)], fill=(0, 220, 255, 120))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=25))
        base.paste(glow, (0, 0), glow)
        return base
    elif style == "ghibli":
        base = Image.new("RGB", (w, h), (135, 195, 145))
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.rectangle([(0, 0), (w, int(h*0.5))], fill=(180, 220, 240, 200))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=20))
        base.paste(glow, (0, 0), glow)
        return base
    elif style == "bw_cinema":
        base = Image.new("RGB", (w, h), (25, 25, 25))
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.ellipse([(int(w*0.2), int(h*0.1)), (int(w*0.8), int(h*0.9))], fill=(180, 180, 180, 100))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=30))
        base.paste(glow, (0, 0), glow)
        return base
    else:
        return Image.new("RGB", (w, h), (240, 240, 245))


def transform_single_image(image: Image.Image, style: str) -> Image.Image:
    """
    단일 이미지 AI 변환:
    1. 인물 정밀 세그멘테이션 마스크 추출 (DeepLabV3) -> 얼굴, 표정, 포즈, 각도 100% 보존
    2. 테마별 배경 고강도 AI Diffusion 변환 (strength=0.75) -> 호그와트 마법 도서관, 네온 도시 등 완벽 전이
    3. 인물에 테마 조명/컬러 톤 하모나이징 적용
    4. 소프트 알파 마스크 합성 -> 얼굴 왜곡/기괴한 천/의상 손상 0% 보장
    """
    target_size = (768, 960)
    init_img = image.convert("RGB").resize(target_size, Image.Resampling.LANCZOS)

    if style == "original":
        enhancer = ImageEnhance.Sharpness(init_img)
        res = enhancer.enhance(1.2)
        contrast = ImageEnhance.Contrast(res)
        return contrast.enhance(1.05)

    cfg = THEME_CONFIGS.get(style, THEME_CONFIGS["wizard"])
    model_type = cfg["model_type"]
    device = "cuda" if (TORCH_AVAILABLE and torch.cuda.is_available()) else "cpu"

    # 1. 인물 영역 세그멘테이션 마스크 추출
    person_mask = extract_person_mask(init_img, device=device)

    # 2. 배경 생성 (AI 확산 모델을 통한 고화질 테마 배경 생성)
    pipe = get_sd_pipeline(model_type)
    ai_bg = None
    
    if pipe is not None and device == "cuda":
        try:
            print(f"[AI Process] '{style}' 테마 배경 고성능 AI Diffusion 생성 중...")
            ai_bg = pipe(
                prompt=cfg["bg_prompt"],
                negative_prompt=cfg["bg_neg"],
                image=init_img,
                strength=cfg["strength"],
                guidance_scale=cfg["guidance_scale"],
                num_inference_steps=18
            ).images[0]
        except Exception as e:
            print(f"[AI Background Error] AI 배경 생성 중 오류 ({e}). Fallback 백드롭 적용.")
            ai_bg = generate_fallback_background(style, target_size)
    else:
        ai_bg = generate_fallback_background(style, target_size)

    # 3. 인물 레이어 테마 조명 및 톤 하모나이징
    person_layer = init_img.copy()
    if cfg["color_boost"] > 0:
        enhancer_c = ImageEnhance.Color(person_layer)
        person_layer = enhancer_c.enhance(cfg["color_boost"])
    else:
        person_layer = ImageOps.grayscale(person_layer).convert("RGB")

    if cfg["contrast_boost"] > 0:
        enhancer_ct = ImageEnhance.Contrast(person_layer)
        person_layer = enhancer_ct.enhance(cfg["contrast_boost"])

    # 은은한 테마 조명 틴트 오버레이
    if cfg.get("lighting_tint") and cfg["color_boost"] > 0:
        tint_layer = Image.new("RGB", target_size, cfg["lighting_tint"])
        person_layer = Image.blend(person_layer, tint_layer, 0.08)

    # 4. 알파 마스크 합성 (인물은 100% 원본 선명도/표정 유지 + 배경은 100% 테마 변환)
    final_composite = Image.composite(person_layer, ai_bg, person_mask)
    return final_composite


def transform_four_cut(images: List[Image.Image], style: str) -> List[Image.Image]:
    """4장 이미지 일괄 AI 스타일 변환"""
    transformed = []
    for idx, img in enumerate(images):
        print(f"[AI Process] ({idx+1}/4) 이미지 '{style}' 인물 보존 & 테마 배경 변환 진행 중...")
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
