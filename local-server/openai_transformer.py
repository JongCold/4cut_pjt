import os
import io
import time
import base64
from typing import List
from PIL import Image, ImageDraw
import openai

# OpenAI API Key는 환경변수(OPENAI_API_KEY) 또는 .env를 통해 주입받습니다.
api_key = os.environ.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key) if api_key else None

# 프롬프트 매핑 (c:\4cuts_pjt\연령변환 프롬프트 규격 100% 준수)
PROMPTS = {
    0: (
        "Transform the people in the input photograph into realistic childhood versions, approximately 6–10 years old. "
        "CRITICAL IDENTITY & POSE PRESERVATION: "
        "- Preserve the exact number of people visible in the input image. Do not add, remove, or duplicate anyone. "
        "- Strictly preserve each person's exact recognizable facial identity, facial structure, eye shape, smile, and glasses (if the person is wearing glasses in the photo, MUST keep the glasses). The child MUST be undeniably and recognizably the SAME person. "
        "- Strictly preserve each person's original pose, body orientation, head tilt, hand gestures, and relative position from the photograph. If they are smiling or making a hand sign, keep the exact same gesture. "
        "- AGE TRANSFORMATION: Give natural child-like facial proportions and soft youthful skin while strictly retaining individual facial identity. Do NOT create babies or toddlers; target elementary school age (6–10 years old). "
        "- CLOTHING: Dress in clean, neat, age-appropriate children's casual clothing. "
        "- RECOMMENDED BACKGROUND: Clean, modern, warm photography studio backdrop with soft pastel lighting (warm beige and soft off-white tones), complementing the childhood theme. "
        "Photorealistic, authentic studio portrait, natural skin texture, realistic shadows, 8k resolution, sharp focus. No cartoon, no anime."
    ),
    1: (
        "Transform the people in the input photograph into realistic teenagers, approximately 15–18 years old. "
        "CRITICAL IDENTITY & POSE PRESERVATION: "
        "- Preserve the exact number of people visible in the input image. Do not add, remove, duplicate, or merge anyone. "
        "- Strictly preserve each person's exact recognizable facial identity, facial bone structure, distinctive facial features, and glasses (if wearing glasses, MUST keep the glasses). The teenager MUST be undeniably and recognizably the SAME person. "
        "- Strictly preserve each person's original pose, body orientation, head posture, hand gestures, and interaction from the photograph. "
        "- CLOTHING & UNIFORM: Dress EVERY visible person in a neat, stylish, realistic Korean-style high school uniform appropriate for their gender (clean blazer jacket, crisp collared shirt, and school tie/ribbon). Realistic fabric, avoid exaggerated costumes. "
        "- AGE TRANSFORMATION: Youthful, clear skin, natural teenage facial features of an authentic high school student. "
        "- RECOMMENDED BACKGROUND: A bright, elegant, modern photography studio portrait background with soft neutral lighting (light gray and subtle beige tones). "
        "Photorealistic photography, natural lighting, realistic skin texture, realistic shadows, 8k resolution, sharp focus. No cartoon, no illustration."
    ),
    3: (
        "Transform the people in the input photograph into dignified, realistic older adults, approximately 65–80 years old. "
        "CRITICAL IDENTITY & POSE PRESERVATION: "
        "- Preserve the exact number of people visible in the input image. Do not add, remove, or duplicate anyone. "
        "- Strictly preserve each person's recognizable facial bone structure, facial identity, eye shape, smile, and glasses (if wearing glasses, MUST keep the glasses). The elderly person MUST be undeniably and recognizably the SAME person. "
        "- Strictly preserve each person's original pose, body orientation, posture, head angle, and hand gestures from the input photograph. "
        "- NATURAL AGING TRANSFORMATION: Apply natural, graceful, realistic aging including gentle facial wrinkles, subtle laugh lines, natural skin texture, and dignified silver/gray hair. Do NOT create exaggerated deformities or hunched postures. "
        "- CLOTHING: Dress in elegant, sophisticated, warm elderly knitwear or classic blazer attire. "
        "- RECOMMENDED BACKGROUND: A warm, classic, dignified photo studio background with gentle ambient lighting and timeless soft neutral aesthetics. "
        "Photorealistic photography, authentic dignified portrait, realistic skin texture, realistic shadows, 8k resolution, sharp focus. No cartoon, no caricature."
    )
}

def transform_single_image_openai(image: Image.Image, cut_index: int, model_name: str = "gpt-image-1.5") -> Image.Image:
    """
    단일 이미지를 받아 OpenAI Edit API(Image-to-Image)를 통해 원본 얼굴/포즈 기반 연령 변환을 수행합니다.
    cut_index: 0(어린이), 1(청소년), 2(원본유지), 3(노년)
    model_name: 기본 'gpt-image-1.5', 고퀄리티 선택 시 'gpt-image-2'
    """
    if cut_index == 2:
        return image.convert("RGB")

    prompt = PROMPTS.get(cut_index, "")
    
    # 1024x1024 고화질 RGB 변환
    img_square = image.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
    
    img_bytes = io.BytesIO()
    img_square.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    
    global client
    if client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            client = openai.OpenAI(api_key=key)
        else:
            print("[OpenAI API Error] OPENAI_API_KEY 환경변수가 설정되지 않아 원본을 유지합니다.")
            return image.convert("RGB")

    try:
        # mask 없이 인풋 이미지를 직접 넘겨 완벽한 Image-to-Image 인물/포즈 보존 변환 수행
        response = client.images.edit(
            model=model_name,
            image=("image.png", img_bytes.getvalue(), "image/png"),
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        item = response.data[0]
        if getattr(item, "b64_json", None):
            img_data = base64.b64decode(item.b64_json)
            edited_img = Image.open(io.BytesIO(img_data)).convert("RGB")
            return edited_img
        elif getattr(item, "url", None):
            import requests
            res = requests.get(item.url, timeout=30)
            edited_img = Image.open(io.BytesIO(res.content)).convert("RGB")
            return edited_img
        else:
            print(f"[OpenAI API Warning] Cut {cut_index}: 응답에 이미지 데이터가 없어 원본을 유지합니다.")
            return image.convert("RGB")
    except Exception as e:
        error_msg = str(e)
        if "unverified_organization" in error_msg:
            print(f"[OpenAI API Error] 조직 인증(Organization Verification)이 필요합니다. platform.openai.com에서 인증을 완료해주세요.")
        else:
            print(f"[OpenAI API Error] Cut {cut_index} (Model: {model_name}): {e}")
        return image.convert("RGB")
