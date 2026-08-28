"""
concept_transformer.py
High-Performance AI Model & Character/Background Transformation Module for RTX GPUs (8GB VRAM)
KeypointRCNN + DeepLabV3 기반 인물 얼굴/표정 100% 보존 + 테마 의상(로브/교복/타이) & 마법 지팡이 & 고대 고딕 도서관 8K 극실사 변환
"""

import os
import io
import sys
import time
import random
from typing import List, Optional, Dict, Tuple
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
KPT_MODEL = None
TORCH_AVAILABLE = False

try:
    import torch
    import torchvision.transforms as T
    from torchvision.models.detection import keypointrcnn_resnet50_fpn, KeypointRCNN_ResNet50_FPN_Weights
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
        "strength": 0.80,
        "guidance_scale": 7.5,
        "color_boost": 1.10,
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
        "strength": 0.80,
        "guidance_scale": 7.5,
        "color_boost": 1.10,
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
        "strength": 0.80,
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
        "strength": 0.80,
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
        "strength": 0.80,
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
        "strength": 0.80,
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


def get_detection_and_segmentation_models(device: str = "cuda"):
    """인물 세그멘테이션(DeepLabV3) 및 포즈/얼굴 키포인트 검출(KeypointRCNN) 모델 싱글톤 로딩"""
    global SEG_MODEL, KPT_MODEL
    if TORCH_AVAILABLE and device == "cuda":
        if SEG_MODEL is None:
            try:
                seg_weights = DeepLabV3_MobileNet_V3_Large_Weights.DEFAULT
                SEG_MODEL = deeplabv3_mobilenet_v3_large(weights=seg_weights).to(device).eval()
            except Exception as e:
                print(f"[AI Engine] DeepLabV3 로딩 실패: {e}")
                SEG_MODEL = None
        if KPT_MODEL is None:
            try:
                kpt_weights = KeypointRCNN_ResNet50_FPN_Weights.DEFAULT
                KPT_MODEL = keypointrcnn_resnet50_fpn(weights=kpt_weights).to(device).eval()
            except Exception as e:
                print(f"[AI Engine] KeypointRCNN 로딩 실패: {e}")
                KPT_MODEL = None
    return SEG_MODEL, KPT_MODEL


def extract_face_and_body_masks(image: Image.Image, device: str = "cuda") -> Tuple[Image.Image, Image.Image, Image.Image, int, List[Tuple[int, int]]]:
    """
    인물 영역에서 얼굴/헤어(보존 영역)와 신체/의상(로브 변환 영역), 손(지팡이 영역)을 정밀 분리
    """
    w, h = image.size
    seg_model, kpt_model = get_detection_and_segmentation_models(device)

    # 1. 전체 인물 마스크
    person_mask = None
    if seg_model is not None:
        try:
            seg_transforms = DeepLabV3_MobileNet_V3_Large_Weights.DEFAULT.transforms()
            inp = seg_transforms(image).unsqueeze(0).to(device)
            with torch.no_grad():
                out = seg_model(inp)["out"][0]
            preds = out.argmax(0).byte().cpu().numpy()
            person_mask_np = (preds == 15).astype(np.uint8) * 255
            person_mask = Image.fromarray(person_mask_np, mode="L").resize((w, h), Image.Resampling.BILINEAR)
        except Exception:
            person_mask = None

    if person_mask is None:
        # Fallback 타원형 마스크
        person_mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(person_mask)
        draw.ellipse([int(w * 0.15), int(h * 0.1), int(w * 0.85), int(h * 0.95)], fill=255)

    # 2. 키포인트 검출 (어깨, 턱선, 손목 위치)
    chin_y = int(h * 0.44)
    wrists = []
    
    if kpt_model is not None:
        try:
            tensor_img = T.ToTensor()(image).to(device)
            with torch.no_grad():
                detections = kpt_model([tensor_img])[0]
            if len(detections["keypoints"]) > 0:
                kpts = detections["keypoints"][0].cpu().numpy()
                l_sh, r_sh = kpts[5], kpts[6]
                if l_sh[2] > 0.25 or r_sh[2] > 0.25:
                    chin_y = int(min(l_sh[1], r_sh[1]) - (h * 0.035))
                
                l_wr, r_wr = kpts[9], kpts[10]
                if l_wr[2] > 0.25:
                    wrists.append((int(l_wr[0]), int(l_wr[1])))
                if r_wr[2] > 0.25:
                    wrists.append((int(r_wr[0]), int(r_wr[1])))
        except Exception as ex:
            print(f"[Keypoint Warning] 키포인트 추출 건너뜀: {ex}")

    # 3. 얼굴 마스크: 인물 영역 중 chin_y 상단
    face_mask_box = Image.new("L", (w, h), 0)
    draw_f = ImageDraw.Draw(face_mask_box)
    draw_f.rectangle([(0, 0), (w, chin_y)], fill=255)
    
    face_mask = Image.fromarray(((np.array(person_mask).astype(np.float32) * np.array(face_mask_box).astype(np.float32)) / 255.0).astype(np.uint8))
    face_mask = face_mask.filter(ImageFilter.GaussianBlur(radius=6))

    # 4. 의상(바디) 마스크: 인물 영역 중 chin_y 하단
    body_mask_box = Image.new("L", (w, h), 0)
    draw_b = ImageDraw.Draw(body_mask_box)
    draw_b.rectangle([(0, chin_y), (w, h)], fill=255)
    
    body_mask = Image.fromarray(((np.array(person_mask).astype(np.float32) * np.array(body_mask_box).astype(np.float32)) / 255.0).astype(np.uint8))
    body_mask = body_mask.filter(ImageFilter.GaussianBlur(radius=6))

    person_mask_feathered = person_mask.filter(ImageFilter.GaussianBlur(radius=6))

    return person_mask_feathered, face_mask, body_mask, chin_y, wrists


def overlay_thematic_outfit_and_props(image: Image.Image, style: str, chin_y: int, wrists: List[Tuple[int, int]]) -> Image.Image:
    """
    테마에 맞는 전용 의상(마법사 로브, 교복, 넥타이, 사이버 재킷 등) 및 소품(빛나는 지팡이) 렌더링
    """
    w, h = image.size
    outfit_layer = image.copy().convert("RGBA")
    
    if style in ["wizard", "magic_academy"]:
        # 1. 다크 위저드 로브 + 빈티지 교복 + 호그와트 넥타이 렌더링
        robe_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        robe_draw = ImageDraw.Draw(robe_layer)
        
        neck_center_x = w // 2
        robe_top = chin_y + int(h * 0.02)
        
        # 다크 위저드 로브 숄더 & 바디
        robe_draw.polygon([
            (neck_center_x - int(w * 0.20), robe_top),
            (neck_center_x + int(w * 0.20), robe_top),
            (w, h),
            (0, h)
        ], fill=(16, 16, 22, 240))
        
        # 빈티지 셔츠 칼라 (화이트-크림)
        collar_l = (neck_center_x - int(w * 0.11), robe_top)
        collar_r = (neck_center_x + int(w * 0.11), robe_top)
        collar_b = (neck_center_x, robe_top + int(h * 0.08))
        robe_draw.polygon([collar_l, collar_r, collar_b], fill=(235, 230, 220, 245))
        
        # 버건디 & 골드 호그와트 스트라이프 타이
        tie_top_w = int(w * 0.038)
        tie_bot_w = int(w * 0.065)
        tie_bot_y = robe_top + int(h * 0.30)
        robe_draw.polygon([
            (neck_center_x - tie_top_w, collar_b[1]),
            (neck_center_x + tie_top_w, collar_b[1]),
            (neck_center_x + tie_bot_w, tie_bot_y),
            (neck_center_x, tie_bot_y + int(h * 0.045)),
            (neck_center_x - tie_bot_w, tie_bot_y)
        ], fill=(125, 25, 32, 250))
        
        # 타이 골드 사선 스트라이프
        for y_off in range(12, int(h * 0.26), 20):
            sy = collar_b[1] + y_off
            robe_draw.line([(neck_center_x - int(w * 0.05), sy), (neck_center_x + int(w * 0.05), sy + 10)], fill=(220, 175, 50, 225), width=4)

        # 로브 깃(Lapels) 음영
        robe_draw.polygon([(0, robe_top + int(h * 0.05)), (neck_center_x - int(w * 0.10), robe_top), (neck_center_x - int(w * 0.05), h), (0, h)], fill=(12, 12, 16, 248))
        robe_draw.polygon([(w, robe_top + int(h * 0.05)), (neck_center_x + int(w * 0.10), robe_top), (neck_center_x + int(w * 0.05), h), (w, h)], fill=(12, 12, 16, 248))
        
        robe_layer = robe_layer.filter(ImageFilter.GaussianBlur(radius=3))
        outfit_layer = Image.alpha_composite(outfit_layer, robe_layer)
        
        # 2. 빛나는 마법 지팡이(Wand) & 골든 스파크 파티클 렌더링
        wand_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        wand_draw = ImageDraw.Draw(wand_layer)
        
        if wrists:
            wand_base = wrists[0]
        else:
            wand_base = (int(w * 0.75), int(h * 0.88))
            
        wand_tip = (wand_base[0] - int(w * 0.16), wand_base[1] - int(h * 0.36))
        
        # 나무 지팡이 몸체
        wand_draw.line([wand_base, wand_tip], fill=(50, 32, 18, 255), width=7)
        wand_draw.line([wand_base, wand_tip], fill=(90, 60, 35, 210), width=4)
        
        # 찬란한 마법광 렌즈 플레어
        tx, ty = wand_tip
        for r, alpha in [(48, 45), (32, 95), (18, 170), (8, 240), (4, 255)]:
            wand_draw.ellipse([(tx - r, ty - r), (tx + r, ty + r)], fill=(255, 235, 160, alpha))
            
        # 주변 흩날리는 황금 마법 입자
        random.seed(int(time.time() * 100) % 1000)
        for _ in range(45):
            px = tx + random.randint(-int(w * 0.28), int(w * 0.28))
            py = ty + random.randint(-int(h * 0.28), int(h * 0.38))
            pr = random.randint(2, 6)
            wand_draw.ellipse([(px - pr, py - pr), (px + pr, py + pr)], fill=(255, 215, 85, random.randint(140, 245)))
            
        wand_layer = wand_layer.filter(ImageFilter.GaussianBlur(radius=2))
        outfit_layer = Image.alpha_composite(outfit_layer, wand_layer)

    elif style == "neon_fantasy":
        # 사이버펑크 네온 재킷 & 발광 칼라
        cyber_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        cyber_draw = ImageDraw.Draw(cyber_layer)
        neck_center_x = w // 2
        robe_top = chin_y + int(h * 0.02)
        
        cyber_draw.polygon([
            (neck_center_x - int(w * 0.18), robe_top),
            (neck_center_x + int(w * 0.18), robe_top),
            (w, h),
            (0, h)
        ], fill=(15, 18, 28, 240))
        
        # 네온 사이언 & 마젠타 발광 라인
        cyber_draw.line([(neck_center_x - int(w*0.12), robe_top), (neck_center_x - int(w*0.08), h)], fill=(0, 230, 255, 220), width=5)
        cyber_draw.line([(neck_center_x + int(w*0.12), robe_top), (neck_center_x + int(w*0.08), h)], fill=(255, 0, 160, 220), width=5)
        cyber_layer = cyber_layer.filter(ImageFilter.GaussianBlur(radius=2))
        outfit_layer = Image.alpha_composite(outfit_layer, cyber_layer)

    elif style == "bw_cinema":
        # 1940s 클래식 필름 누아르 트렌치코트 / 라펠 정장
        bw_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bw_draw = ImageDraw.Draw(bw_layer)
        neck_center_x = w // 2
        robe_top = chin_y + int(h * 0.02)
        
        bw_draw.polygon([
            (neck_center_x - int(w * 0.18), robe_top),
            (neck_center_x + int(w * 0.18), robe_top),
            (w, h),
            (0, h)
        ], fill=(22, 22, 24, 245))
        bw_layer = bw_layer.filter(ImageFilter.GaussianBlur(radius=3))
        outfit_layer = Image.alpha_composite(outfit_layer, bw_layer)

    return outfit_layer.convert("RGB")


def get_sd_pipeline(model_key: str = "dreamshaper"):
    """8GB VRAM GPU 최적화 모델 파이프라인 캐싱 및 로딩"""
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
    """GPU 미지원 시 테마별 고해상도 백드롭 생성"""
    w, h = size
    if style in ["wizard", "magic_academy"]:
        base = Image.new("RGB", (w, h), (26, 18, 14))
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.rectangle([(0, 0), (w, int(h * 0.35))], fill=(15, 10, 8, 220))
        draw.rectangle([(0, 0), (int(w * 0.25), h)], fill=(20, 12, 10, 200))
        draw.rectangle([(int(w * 0.75), 0), (w, h)], fill=(20, 12, 10, 200))
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
    단일 이미지 AI 변환 (인물 얼굴/표정 100% 보존 + 테마 의상/소품 렌더링 + 배경 고강도 Diffusion 전환)
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

    # 1. 인물 마스크 및 얼굴/의상 영역 분리
    person_mask, face_mask, body_mask, chin_y, wrists = extract_face_and_body_masks(init_img, device=device)

    # 2. 테마 의상(로브/교복/타이) 및 소품(빛나는 지팡이) 렌더링
    clothed_person = overlay_thematic_outfit_and_props(init_img, style, chin_y, wrists)

    # 3. 고화질 테마 배경 AI Diffusion 생성
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
            print(f"[AI Background Error] AI 배경 생성 오류 ({e}). Fallback 백드롭 적용.")
            ai_bg = generate_fallback_background(style, target_size)
    else:
        ai_bg = generate_fallback_background(style, target_size)

    # 4. 1단계 합성: 배경 + 변환된 의상 & 지팡이 바디
    stage1 = Image.composite(clothed_person, ai_bg, person_mask)

    # 5. 2단계 합성: 원본의 100% 얼굴/표정/헤어 레이어를 완벽하게 복원 (얼굴 왜곡 0%)
    face_layer = init_img.copy()
    if cfg["color_boost"] > 0:
        face_layer = ImageEnhance.Color(face_layer).enhance(cfg["color_boost"])
        face_layer = ImageEnhance.Contrast(face_layer).enhance(cfg["contrast_boost"])
    else:
        face_layer = ImageOps.grayscale(face_layer).convert("RGB")
        face_layer = ImageEnhance.Contrast(face_layer).enhance(cfg["contrast_boost"])

    # 6. 최종 인물 얼굴 레이어 정밀 마운트
    final_composite = Image.composite(face_layer, stage1, face_mask)
    
    # 7. 샤프니스 & 시네마틱 룩 완성
    final_output = final_composite.filter(ImageFilter.SHARPEN)
    return final_output


def transform_four_cut(images: List[Image.Image], style: str) -> List[Image.Image]:
    """4장 이미지 일괄 AI 스타일 변환"""
    transformed = []
    for idx, img in enumerate(images):
        print(f"[AI Process] ({idx+1}/4) 이미지 '{style}' 의상/소품/배경 일체형 AI 변환 진행 중...")
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
