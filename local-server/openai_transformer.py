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

# 프롬프트 매핑 (원본 골격 100% 보존, DSLR 85mm f/2.8 스튜디오 실사 및 과도한 스무딩 배제 규격)
PROMPTS = {
    0: (
        "Ultra-realistic studio portrait of the people in the input photograph transformed into authentic childhood versions, approximately 6–10 years old. "
        "CRITICAL ANATOMICAL IDENTITY & BONE STRUCTURE PRESERVATION: "
        "- Preserve the exact number of people visible in the input image. Do not add, remove, or duplicate anyone. "
        "- Strictly anchor and preserve each person's unique facial bone structure, jawline contours, cheekbones, exact eye shape and eye slant, eyebrow arch, nose bridge and nostril shape, philtrum, and mouth contours directly derived from the input photograph. "
        "- The child MUST be undeniably and recognizably the EXACT same individual in their elementary school years, retaining their unique biological facial geometry. Do NOT replace the face with a generic, unrelated child's face. "
        "- If the subject wears glasses in the photo, preserve the exact glasses style, frame color, and shape, fitted naturally to the child's facial proportions. "
        "- Strictly preserve each person's original pose, body orientation, head tilt, hand gestures, and relative position from the photograph. "
        "HYPER-REALISTIC SKIN TEXTURE & COMPLEXION (ZERO OVER-SMOOTHING): "
        "- Natural authentic child skin texture with delicate micro-textures, fine visible pores, faint natural smile lines, and a healthy youthful complexion without over-smoothing. "
        "- Absolutely NO over-smoothing, NO airbrushing, NO porcelain plastic look. True-to-life natural skin tones. "
        "CLOTHING & BACKGROUND: "
        "- Neat, clean, age-appropriate children's casual everyday clothing (elementary school age). "
        "- Clean, neutral seamless photography studio backdrop with soft warm tones (gentle beige or off-white). "
        "STUDIO DSLR PHOTOGRAPHY SPECIFICATIONS: "
        "- Shot on full-frame DSLR camera, 85mm prime portrait lens, f/2.8 aperture. "
        "- Soft directional key light with gentle falloff, balanced ambient fill, natural catchlights in the pupils, realistic soft shadows, sharp optical focus on eyes and facial contours, subtle shallow depth of field, true-to-life RAW photo colors. "
        "STRICT EXCLUSIONS & NEGATIVE CONSTRAINTS: "
        "plastic skin, porcelain face, doll-like artificial appearance, airbrushed smoothness, heavy beauty retouching, beauty filter, waxy skin, generic child face template, altered jawline or lost facial identity, cartoonish smoothing, CGI, 3D render, digital illustration, anime, blur, distortion, babies, toddlers."
    ),
    1: (
        "Ultra-realistic studio portrait of the people in the input photograph transformed into authentic teenagers, approximately 15–18 years old. "
        "CRITICAL ANATOMICAL IDENTITY & BONE STRUCTURE PRESERVATION: "
        "- Preserve the exact number of people visible in the input image. Do not add, remove, duplicate, or merge anyone. "
        "- Strictly preserve each person's unique facial bone structure, jawline contours, cheekbones, distinctive eye shape, eyelid creases, eyebrow curve, nose bridge, and lip contours directly from the input photograph. "
        "- The teenager MUST be undeniably and recognizably the EXACT same individual during their high school years, maintaining their personal facial features and biometric proportions. Do NOT substitute with a generic idol or model face. "
        "- If wearing glasses, preserve the exact glasses frame, shape, and placement naturally on their face. "
        "- Strictly preserve each person's original pose, head posture, body orientation, hand gestures, and interaction from the photograph. "
        "HYPER-REALISTIC SKIN TEXTURE (ZERO OVER-SMOOTHING): "
        "- Youthful, natural teenage skin texture with authentic micro-details, visible fine pores, subtle natural skin creases, healthy balanced complexion without heavy makeup or artificial smoothing. "
        "CLOTHING & UNIFORM: "
        "- Neat, stylish, realistic Korean-style high school uniform appropriate for gender (clean tailored blazer jacket, crisp collared shirt, and school tie/ribbon) with realistic fabric textures and natural folds. "
        "STUDIO DSLR PHOTOGRAPHY SPECIFICATIONS & LIGHTING: "
        "- Shot on professional DSLR camera, 85mm prime lens, f/2.8, sharp focus on facial features. "
        "- Soft directional key light with gentle falloff, clean neutral seamless photography studio background (subtle light gray and soft beige tones), shallow depth of field, authentic true-to-life colors. "
        "STRICT EXCLUSIONS & NEGATIVE CONSTRAINTS: "
        "plastic skin, porcelain doll face, airbrushed smoothness, heavy retouching, beauty filter, over-smoothed skin, generic anime/idol face, altered bone structure, CGI, 3D render, cartoon, digital painting, blur, distortion, adult or child appearance."
    ),
    3: (
        "Ultra-realistic studio portrait of the people in the input photograph transformed into dignified, realistic older adults, approximately 65–80 years old. "
        "CRITICAL ANATOMICAL IDENTITY & BONE STRUCTURE PRESERVATION: "
        "- Preserve the exact number of people visible in the input image. Do not add, remove, or duplicate anyone. "
        "- Strictly preserve each person's recognizable facial bone structure, jawline, eye shape, eyelid folds, eyebrow structure, nose contour, and mouth shape from the input photograph. "
        "- The elderly person MUST be undeniably and recognizably the EXACT same individual gracefully aged, preserving their unique facial identity and expressions. "
        "- If wearing glasses, preserve the exact glasses style, frame, and fit naturally on the aged face. "
        "- Strictly preserve each person's original pose, posture, head tilt, body angle, and hand gestures. "
        "GRACEFUL NATURAL AGING & HYPER-REALISTIC SKIN TEXTURE: "
        "- Natural, authentic aging anchored to the subject's own facial structure: subtle laugh lines, fine crow's feet around eyes, natural forehead lines, realistic skin texture with visible pores and natural aged skin elasticity. "
        "- Dignified silver/gray hair with realistic hair strand texture and natural volume. Avoid grotesque deformities, excessive hollow cheeks, or extreme uncharacteristic wrinkles. "
        "CLOTHING & AMBIENCE: "
        "- Elegant, sophisticated, warm elderly knitwear or classic tailored blazer attire with authentic fabric texture. "
        "- Clean, classic, dignified photography studio background with warm neutral ambient lighting. "
        "STUDIO DSLR PHOTOGRAPHY SPECIFICATIONS: "
        "- Shot on full-frame DSLR camera, 85mm portrait lens, f/2.8 aperture, sharp optical focus on eyes and facial contours, shallow depth of field. "
        "- Soft directional key light with gentle falloff, natural warm catchlights in the eyes, realistic shadows, authentic RAW photograph color grading. "
        "STRICT EXCLUSIONS & NEGATIVE CONSTRAINTS: "
        "plastic skin, porcelain face, airbrushed smoothness, heavy retouching, artificial mask, exaggerated grotesque wrinkles, hunchback, cartoon, caricature, CGI, 3D render, distortion, blur."
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
