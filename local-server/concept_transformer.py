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


def hex_to_rgb(hex_color: str, default: Tuple[int, int, int] = (255, 253, 249)) -> Tuple[int, int, int]:
    """HEX 색상 문자열을 RGB 튜플로 변환"""
    if not hex_color:
        return default
    s = hex_color.strip().lstrip('#')
    if len(s) == 6:
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except Exception:
            return default
    return default


def is_dark_color(rgb: Tuple[int, int, int]) -> bool:
    """배경 밝기(Luminance) 판별: 어두운 배경일 경우 True"""
    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return lum < 140


def draw_barcode_vector(draw: ImageDraw.ImageDraw, center_x: int, center_y: int, h: int, color: Tuple[int, int, int]):
    """1번 프리뷰 이미지와 완벽히 동일한 세로 바코드 벡터 시뮬레이션 렌더링"""
    bar_widths = [3, 1, 4, 2, 5, 2, 1, 4, 2, 4, 3, 5, 2, 1, 4, 2, 3, 1, 5, 2, 4, 1, 3, 2, 5, 1, 4]
    sum_w = sum(bar_widths) + (len(bar_widths) - 1) * 3
    start_x = center_x - (sum_w // 2)
    top_y = center_y - (h // 2)
    bot_y = center_y + (h // 2)
    
    cur_x = start_x
    for bw in bar_widths:
        draw.rectangle([cur_x, top_y, cur_x + bw, bot_y], fill=color)
        cur_x += bw + 3


def render_neobrutalism_4cut(
    images: List[Image.Image],
    canvas_w: int,
    canvas_h: int,
    brand_title: str = "AI 4-CUT STUDIO",
    frame_color: str = "#FFFDF9",
    text_color: Optional[str] = None
) -> Image.Image:
    """
    1번 웹 프리뷰 이미지와 100% 동일한 네오브루탈리즘 감성 인생4컷 프레임 렌더러
    - 좌상단: 노란색 기울어진 '최종 인화본 ✨' 스티커 뱃지
    - 우상단: 붉은색 원형 '通' 인장 도장 스탬프
    - 카드 본체: 둥근 모서리, 볼드 잉크 라인, 하드 드롭 섀도우
    - 2x2 슬롯: ImageOps.fit (상하/좌우 여백 0% 완벽 일치)
    - 사진 하단: 테마 타이틀 & MEMORY PHOTO 일시
    - 중간 티켓 점선 절취선 (Dashed Divider)
    - 하단 푸터: '청년4컷 스튜디오' + 날짜 + 세로 바코드 + '서울청년센터 영등포 × 놀면뭐AI'
    - 프레임 테두리 색상: 크림, 블랙, 레드, 네이비 등 사용자가 고른 색상 100% 반영
    """
    scale = canvas_w / 900.0  # 900px 기준 스케일 팩터

    # 1. 폰트 로드
    font_bold_lg = None
    font_bold_md = None
    font_bold_sm = None
    font_sub = None
    font_stamp = None

    font_path = "C:/Windows/Fonts/malgunbd.ttf"
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/malgun.ttf"

    try:
        font_bold_lg = ImageFont.truetype(font_path, int(24 * scale))
        font_bold_md = ImageFont.truetype(font_path, int(20 * scale))
        font_bold_sm = ImageFont.truetype(font_path, int(15 * scale))
        font_sub = ImageFont.truetype(font_path, int(13 * scale))
        font_stamp = ImageFont.truetype(font_path, int(26 * scale))
    except Exception:
        font_bold_lg = ImageFont.load_default()
        font_bold_md = ImageFont.load_default()
        font_bold_sm = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_stamp = ImageFont.load_default()

    # 2. 색상 설정
    card_bg_rgb = hex_to_rgb(frame_color, (255, 253, 249))
    dark_mode = is_dark_color(card_bg_rgb)

    if text_color:
        txt_main_rgb = hex_to_rgb(text_color, (255, 255, 255) if dark_mode else (30, 35, 42))
    else:
        txt_main_rgb = (255, 255, 255) if dark_mode else (30, 35, 42)

    txt_sub_rgb = (200, 205, 215) if dark_mode else (120, 130, 145)
    line_rgb = (255, 255, 255, 130) if dark_mode else (190, 205, 220)
    slot_border_rgb = (255, 255, 255, 160) if dark_mode else (215, 220, 228)
    ink_border_rgb = (28, 25, 23)
    hard_shadow_rgb = (28, 25, 23)

    # 3. 캔버스 생성 (은은한 크림 캔버스 + 도트 그리드)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (250, 246, 239))
    c_draw = ImageDraw.Draw(canvas)

    # 도트 그리드 백그라운드
    dot_spacing = int(24 * scale)
    dot_color = (222, 216, 204)
    for x in range(dot_spacing // 2, canvas_w, dot_spacing):
        for y in range(dot_spacing // 2, canvas_h, dot_spacing):
            c_draw.point((x, y), fill=dot_color)

    # 4. 네오브루탈리즘 카드 레이아웃 계산
    card_margin_x = int(45 * scale)
    card_margin_top = int(42 * scale)
    card_w = canvas_w - (card_margin_x * 2)
    card_h = canvas_h - (card_margin_top * 2) - int(10 * scale)

    card_x = card_margin_x
    card_y = card_margin_top
    radius = int(22 * scale)
    shadow_offset = int(8 * scale)
    border_w = max(3, int(3.5 * scale))

    # 하드 드롭 섀도우
    c_draw.rounded_rectangle(
        [card_x + shadow_offset, card_y + shadow_offset, card_x + card_w + shadow_offset, card_y + card_h + shadow_offset],
        radius=radius,
        fill=hard_shadow_rgb
    )

    # 카드 본체 배경 및 외곽 테두리
    c_draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=radius,
        fill=card_bg_rgb,
        outline=ink_border_rgb,
        width=border_w
    )

    # 5. 2x2 사진 슬롯 계산
    inner_pad_x = int(32 * scale)
    inner_pad_top = int(40 * scale)
    slot_gap = int(14 * scale)

    photo_area_w = card_w - (inner_pad_x * 2)
    slot_w = (photo_area_w - slot_gap) // 2
    # 4:5에 최적화된 슬롯 높이 비율
    slot_h = int(slot_w * 1.26)

    positions = [
        (card_x + inner_pad_x, card_y + inner_pad_top),
        (card_x + inner_pad_x + slot_w + slot_gap, card_y + inner_pad_top),
        (card_x + inner_pad_x, card_y + inner_pad_top + slot_h + slot_gap),
        (card_x + inner_pad_x + slot_w + slot_gap, card_y + inner_pad_top + slot_h + slot_gap)
    ]

    for idx, img in enumerate(images[:4]):
        img_rgb = img.convert("RGB")
        # 어떤 비율/해상도라도 1px 오차 없이 100% 꽉 차게 Center Crop Fit
        img_fitted = ImageOps.fit(img_rgb, (slot_w, slot_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        
        pos = positions[idx]
        slot_x, slot_y = pos
        canvas.paste(img_fitted, (slot_x, slot_y))

        # 슬롯 테두리
        c_draw.rectangle(
            [slot_x, slot_y, slot_x + slot_w, slot_y + slot_h],
            outline=slot_border_rgb if not dark_mode else (255, 255, 255),
            width=max(1, int(1.5 * scale))
        )

    # 6. 사진 하단 텍스트 (테마 타이틀 & 일시)
    photo_area_bottom = card_y + inner_pad_top + (slot_h * 2) + slot_gap
    text_center_x = card_x + (card_w // 2)

    title_y = photo_area_bottom + int(34 * scale)
    date_y = photo_area_bottom + int(60 * scale)

    c_draw.text((text_center_x, title_y), brand_title, fill=txt_main_rgb, font=font_bold_md, anchor="mm")

    now_str = datetime.now().strftime("%Y.%m.%d | %H:%M")
    c_draw.text((text_center_x, date_y), f"MEMORY PHOTO • {now_str}", fill=txt_sub_rgb, font=font_sub, anchor="mm")

    # 7. 티켓 점선 절취선 (Dashed Line)
    dash_y = photo_area_bottom + int(85 * scale)
    dash_start_x = card_x + int(24 * scale)
    dash_end_x = card_x + card_w - int(24 * scale)
    dash_len = int(10 * scale)
    dash_gap = int(7 * scale)

    cur_x = dash_start_x
    dash_col = (255, 255, 255) if dark_mode else (180, 195, 210)
    while cur_x < dash_end_x:
        next_x = min(cur_x + dash_len, dash_end_x)
        c_draw.line([(cur_x, dash_y), (next_x, dash_y)], fill=dash_col, width=max(2, int(2.5 * scale)))
        cur_x += dash_len + dash_gap

    # 8. 하단 푸터 영역
    footer_row1_y = dash_y + int(32 * scale)
    left_label_x = card_x + int(36 * scale)
    right_date_x = card_x + card_w - int(36 * scale)

    # 8.1 좌측: '청년4컷 스튜디오', 우측: 현재 날짜 ('2026.09.12')
    today_str = datetime.now().strftime("%Y.%m.%d")
    c_draw.text((left_label_x, footer_row1_y), "청년4컷 스튜디오", fill=txt_main_rgb, font=font_bold_md, anchor="lm")
    c_draw.text((right_date_x, footer_row1_y), today_str, fill=txt_sub_rgb, font=font_bold_sm, anchor="rm")

    # 8.2 중앙: 세로 바코드 벡터 그래픽
    barcode_y = footer_row1_y + int(35 * scale)
    barcode_h = int(32 * scale)
    barcode_color = (255, 255, 255) if dark_mode else (30, 35, 42)
    draw_barcode_vector(c_draw, text_center_x, barcode_y, barcode_h, barcode_color)

    # 8.3 하단 중앙: '서울청년센터 영등포 × 놀면뭐AI'
    branding_y = barcode_y + int(34 * scale)
    c_draw.text((text_center_x, branding_y), "서울청년센터 영등포 × 놀면뭐AI", fill=txt_sub_rgb, font=font_sub, anchor="mm")

    # 9. 상단 장식 오버레이 (좌상단 '최종 인화본' 스티커 + 우상단 '通' 붉은 도장)
    # 9.1 노란색 스티커 뱃지 (회전 -4도)
    st_w = int(176 * scale)
    st_h = int(46 * scale)
    sticker_img = Image.new("RGBA", (st_w + 30, st_h + 30), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(sticker_img)
    
    s_box = [15, 15, 15 + st_w, 15 + st_h]
    s_draw.rounded_rectangle(s_box, radius=int(8 * scale), fill=(255, 227, 112, 255), outline=ink_border_rgb, width=max(2, int(2.5 * scale)))
    
    # 텍스트 라벨 (폰트 이모지 깨짐 없는 한글 볼드 텍스트)
    s_draw.text((15 + int(24 * scale), 15 + (st_h // 2) - int(1 * scale)), "최종 인화본", fill=ink_border_rgb, font=font_bold_sm, anchor="lm")
    
    # 반짝이 별(✨) 벡터 도형 렌더링
    star_cx = 15 + st_w - int(30 * scale)
    star_cy = 15 + (st_h // 2) - int(1 * scale)
    star_r = int(9 * scale)
    star_pts = [
        (star_cx, star_cy - star_r),
        (star_cx + int(star_r * 0.3), star_cy - int(star_r * 0.3)),
        (star_cx + star_r, star_cy),
        (star_cx + int(star_r * 0.3), star_cy + int(star_r * 0.3)),
        (star_cx, star_cy + star_r),
        (star_cx - int(star_r * 0.3), star_cy + int(star_r * 0.3)),
        (star_cx - star_r, star_cy),
        (star_cx - int(star_r * 0.3), star_cy - int(star_r * 0.3)),
    ]
    s_draw.polygon(star_pts, fill=(245, 166, 35, 255), outline=ink_border_rgb)
    
    sticker_rot = sticker_img.rotate(-4, resample=Image.Resampling.BICUBIC, expand=True)
    sticker_pos = (card_x - int(10 * scale), card_y - int(16 * scale))
    canvas.paste(sticker_rot, sticker_pos, sticker_rot)

    # 9.2 우상단 '通' 붉은색 인장 도장
    stamp_d = int(58 * scale)
    stamp_img = Image.new("RGBA", (stamp_d, stamp_d), (0, 0, 0, 0))
    st_draw = ImageDraw.Draw(stamp_img)
    st_draw.ellipse([2, 2, stamp_d - 3, stamp_d - 3], fill=(185, 56, 38, 255), outline=ink_border_rgb, width=max(2, int(2.5 * scale)))
    st_draw.ellipse([int(6 * scale), int(6 * scale), stamp_d - int(7 * scale), stamp_d - int(7 * scale)], outline=(255, 255, 255, 220), width=max(1, int(1.5 * scale)))
    st_draw.text((stamp_d // 2, stamp_d // 2 - int(1 * scale)), "通", fill=(255, 255, 255, 255), font=font_stamp, anchor="mm")

    stamp_pos = (card_x + card_w - stamp_d + int(10 * scale), card_y - int(10 * scale))
    canvas.paste(stamp_img, stamp_pos, stamp_img)

    return canvas


def create_4cut_frame(
    images: List[Image.Image],
    brand_title: str = "AI 4-CUT STUDIO",
    frame_color: str = "#FFFDF9",
    text_color: Optional[str] = None
) -> Image.Image:
    """
    3:4 ~ 2:3 비율 (가로 900px, 세로 1350px) 네오브루탈리즘 완성형 인생네컷 프레임 합성
    - 1번 웹 프리뷰 이미지와 완벽히 동일한 디자인 & 컬러 반영
    """
    return render_neobrutalism_4cut(
        images=images,
        canvas_w=900,
        canvas_h=1350,
        brand_title=brand_title,
        frame_color=frame_color,
        text_color=text_color
    )


def create_4cut_frame_postcard(
    images: List[Image.Image],
    brand_title: str = "AI 4-CUT STUDIO",
    frame_color: str = "#FFFDF9",
    text_color: Optional[str] = None
) -> Image.Image:
    """
    Canon SELPHY CP1500 엽서(Postcard 4x6인치) 300 DPI 규격 (1200 x 1800 px)
    - 1번 웹 프리뷰와 100% 동일한 네오브루탈리즘 감성 인생4컷 카드 고해상도 출력용 프레임
    - 선택된 프레임 테두리 색상(크림, 블랙, 레드, 네이비) 실시간 반영
    """
    return render_neobrutalism_4cut(
        images=images,
        canvas_w=1200,
        canvas_h=1800,
        brand_title=brand_title,
        frame_color=frame_color,
        text_color=text_color
    )



def create_test_pattern_postcard(printer_name: str = "Canon SELPHY CP1500") -> Image.Image:
    """
    현장 셋업 점검용 4x6 엽서 (1200x1800 300DPI) 테스트 패턴 생성
    - 색감 점검용 4색 CMYK / RGB 바
    - 2분할 절취선 및 슬롯 정렬 그리드
    - 네트워크 및 하드웨어 테스트 정보 표기
    """
    canvas_w = 1200
    canvas_h = 1800
    frame = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(frame)

    brand_font = None
    sub_font = None
    for fp in ["C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
        if os.path.exists(fp):
            try:
                brand_font = ImageFont.truetype(fp, 36)
                sub_font = ImageFont.truetype(fp, 22)
                break
            except Exception:
                continue
    if not brand_font:
        brand_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()

    strip_w = 600
    colors = [
        ("YELLOW (1-Pass)", (250, 204, 21)),
        ("MAGENTA (2-Pass)", (244, 63, 94)),
        ("CYAN (3-Pass)", (14, 165, 233)),
        ("BLACK (K)", (30, 41, 59))
    ]

    for offset_x in [0, strip_w]:
        # 스트립 테두리
        draw.rectangle([offset_x + 30, 30, offset_x + strip_w - 30, canvas_h - 30], outline=(203, 213, 225), width=3)
        
        # 타이틀
        draw.text((offset_x + strip_w // 2, 80), "PRINTER DIAGNOSTICS TEST", fill=(15, 23, 42), font=brand_font, anchor="mm")
        draw.text((offset_x + strip_w // 2, 130), f"Device: {printer_name}", fill=(71, 85, 105), font=sub_font, anchor="mm")
        
        # 색상 테스트 바
        y_c = 190
        for name, col in colors:
            draw.rectangle([offset_x + 60, y_c, offset_x + strip_w - 60, y_c + 140], fill=col, outline=(148, 163, 184), width=1)
            draw.text((offset_x + strip_w // 2, y_c + 70), name, fill=(255, 255, 255) if col != (250, 204, 21) else (30, 41, 59), font=sub_font, anchor="mm")
            y_c += 170

        # 그라디언트/해상도 라인 테스트
        y_g = y_c + 20
        draw.rectangle([offset_x + 60, y_g, offset_x + strip_w - 60, y_g + 260], outline=(203, 213, 225), width=2)
        draw.text((offset_x + strip_w // 2, y_g + 35), "300 DPI ALIGNMENT GRID", fill=(71, 85, 105), font=sub_font, anchor="mm")
        
        # 정렬 라인
        for ly in range(y_g + 70, y_g + 240, 25):
            draw.line([(offset_x + 80, ly), (offset_x + strip_w - 80, ly)], fill=(226, 232, 240), width=2)
        draw.line([(offset_x + strip_w // 2, y_g + 60), (offset_x + strip_w // 2, y_g + 245)], fill=(148, 163, 184), width=2)

        # 시스템 정보 & 시간
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.text((offset_x + strip_w // 2, canvas_h - 220), "AI 4-CUT STUDIO KIOSK", fill=(109, 40, 217), font=brand_font, anchor="mm")
        draw.text((offset_x + strip_w // 2, canvas_h - 160), f"Test Date: {now_str}", fill=(100, 116, 139), font=sub_font, anchor="mm")
        draw.text((offset_x + strip_w // 2, canvas_h - 110), "Status: 100x148mm Postcard OK", fill=(16, 185, 129), font=sub_font, anchor="mm")

    # 중앙 절취선
    for y in range(30, canvas_h - 30, 30):
        draw.line([(strip_w, y), (strip_w, y + 16)], fill=(203, 213, 225), width=2)

    return frame

