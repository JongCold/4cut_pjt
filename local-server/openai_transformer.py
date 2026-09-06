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

# 프롬프트 매핑 (0: 어린이, 1: 청소년, 2: 원본유지(호출 생략됨), 3: 노년)
PROMPTS = {
    0: "Transform the people in the input photograph into realistic childhood versions, approximately 6-10 years old. Give each person natural child-like facial proportions. Keep the background simple and neutral. Photorealistic photography.",
    1: "Transform the people in the input photograph into realistic teenagers, approximately 15-18 years old, wearing Korean high school uniforms. Keep the background simple and neutral. Photorealistic photography.",
    3: "Transform the people in the input photograph into realistic older adults, approximately 65-80 years old, with natural aging wrinkles and gray hair. Keep the background simple and neutral. Photorealistic photography."
}

def transform_single_image_openai(image: Image.Image, cut_index: int, model_name: str = "gpt-image-1.5") -> Image.Image:
    """
    단일 이미지를 받아 OpenAI Edit API를 통해 연령 변환을 수행합니다.
    cut_index: 0(어린이), 1(청소년), 2(원본유지), 3(노년)
    model_name: 기본 'gpt-image-1.5', 고퀄리티 선택 시 'gpt-image-2'
    """
    if cut_index == 2:
        return image.convert("RGB")

    prompt = PROMPTS.get(cut_index, "")
    
    # DALL-E 2 Edit API 요구사항: 1024x1024 투명 PNG, 4MB 이하
    img_square = image.convert("RGBA").resize((1024, 1024), Image.Resampling.LANCZOS)
    
    # 마스크 생성: 투명 영역을 재생성
    mask = Image.new("RGBA", (1024, 1024), (255, 255, 255, 255))
    draw = ImageDraw.Draw(mask)
    draw.rectangle([(150, 150), (874, 950)], fill=(255, 255, 255, 0))
    
    img_bytes = io.BytesIO()
    img_square.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    
    mask_bytes = io.BytesIO()
    mask.save(mask_bytes, format="PNG")
    global client
    if client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            client = openai.OpenAI(api_key=key)
        else:
            print("[OpenAI API Error] OPENAI_API_KEY 환경변수가 설정되지 않아 원본을 유지합니다.")
            return image.convert("RGB")

    try:
        response = client.images.edit(
            model=model_name,
            image=("image.png", img_bytes.getvalue(), "image/png"),
            mask=("mask.png", mask_bytes.getvalue(), "image/png"),
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
