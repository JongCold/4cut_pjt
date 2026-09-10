import os
import io
import time
import base64
from typing import List
from PIL import Image, ImageDraw, ImageFilter
import openai

# OpenAI API Key는 환경변수(OPENAI_API_KEY) 또는 .env를 통해 주입받습니다.
api_key = os.environ.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key) if api_key else None

# 프롬프트 매핑 (제로 블러, 클린 단색 스튜디오 사이클로라마 배경 교체, 조명 명암 분리 및 실사 텍스처 규격)
PROMPTS = {
    0: (
        "Ultra-realistic studio portrait of the people in the input photograph transformed into authentic childhood versions, approximately 6–10 years old. "
        "CRITICAL MULTI-PERSON INDIVIDUAL SUBJECT PRESERVATION: "
        "- Preserve the exact number of people visible in the input image. Do not add, remove, duplicate, or merge anyone. "
        "- RECOGNIZE AND TREAT EVERY SINGLE PERSON AS AN INDEPENDENT PRIMARY SUBJECT: If there are multiple people (e.g. 2 or more people), every individual must be individually identified and transformed into their own childhood counterpart with equal clarity, detail, and anatomical fidelity. "
        "- Strictly anchor and preserve each person's unique facial bone structure, jawline contours, cheekbones, exact eye shape and eye slant, eyebrow arch, nose bridge and nostril shape, philtrum, and mouth contours directly derived from their respective face in the photograph. "
        "- The child versions MUST be undeniably and recognizably the EXACT same individuals in their elementary school years, retaining their individual biological facial geometry. Do NOT replace any face with a generic, unrelated child's face. "
        "- If any subject wears glasses in the photo, preserve the exact glasses style, frame color, and shape, fitted naturally to the child's facial proportions. "
        "- Strictly preserve each person's original pose, body orientation, head tilt, hand gestures, and relative position from the photograph. "
        "- DEBLUR & SHARPEN RESTORATION: Actively deblur, sharpen, and restore all facial features, eyes, and skin texture into crisp, crystal-clear focus. No person should be left blurry. "
        "HYPER-REALISTIC SKIN TEXTURE & COMPLEXION (ZERO OVER-SMOOTHING): "
        "- Natural authentic child skin texture with delicate micro-textures, fine visible pores, faint natural smile lines, and a healthy youthful complexion without over-smoothing. "
        "- Absolutely NO over-smoothing, NO airbrushing, NO porcelain plastic look. True-to-life natural skin tones. "
        "CLOTHING & ATTIRE: "
        "- Neat, clean, age-appropriate children's casual everyday clothing (elementary school age). "
        "SEAMLESS STUDIO BACKDROP & THREE-POINT LIGHTING (ZERO OPTICAL BLUR): "
        "- Background is a completely clean, solid, seamless photography studio cyclorama wall in soft neutral warm beige tones. "
        "- ABSOLUTELY ZERO OPTICAL BLUR, ZERO BOKEH, NO SHALLOW DEPTH OF FIELD. Dimensional subject separation is achieved purely through directional studio key lighting, balanced ambient fill, natural catchlights in every pupil, and tonal contrast against the solid wall, NOT through lens blurring. "
        "STUDIO OPTICS & FULL PAN-FOCUS SPECIFICATIONS: "
        "- Professional studio camera, f/8 group portrait aperture, deep pan-focus across ALL subjects in the frame. "
        "- Uniform, razor-sharp optical focus across EVERY person from edge to edge without any out-of-focus areas. "
        "STRICT EXCLUSIONS & NEGATIVE CONSTRAINTS: "
        "plastic skin, porcelain face, doll-like artificial appearance, airbrushed smoothness, heavy beauty retouching, beauty filter, waxy skin, generic child face template, altered jawline or lost facial identity, cartoonish smoothing, CGI, 3D render, digital illustration, anime, babies, toddlers, bokeh, shallow depth of field, background blur, out-of-focus blur, blurry background, artificial blurring, lens blur, selective focus blurring other people, out-of-focus background person, blurry secondary face, motion blur, partial blur on human bodies, depth-of-field blur on faces."
    ),
    1: (
        "Ultra-realistic studio portrait of the people in the input photograph transformed into authentic teenagers, approximately 15–18 years old. "
        "CRITICAL MULTI-PERSON INDIVIDUAL SUBJECT PRESERVATION: "
        "- Preserve the exact number of people visible in the input image. Do not add, remove, duplicate, or merge anyone. "
        "- RECOGNIZE AND TREAT EVERY SINGLE PERSON AS AN INDEPENDENT PRIMARY SUBJECT: If there are multiple people (e.g. 2 or more people), every individual must be individually identified and transformed into their own teenage counterpart with equal clarity, detail, and anatomical fidelity. "
        "- Strictly preserve each person's unique facial bone structure, jawline contours, cheekbones, distinctive eye shape, eyelid creases, eyebrow curve, nose bridge, and lip contours directly from their respective face in the input photograph. "
        "- The teenagers MUST be undeniably and recognizably the EXACT same individuals during their high school years, maintaining their personal facial features and biometric proportions. Do NOT substitute with generic idol or model faces. "
        "- If wearing glasses, preserve the exact glasses frame, shape, and placement naturally on their face. "
        "- Strictly preserve each person's original pose, head posture, body orientation, hand gestures, and interaction from the photograph. "
        "- DEBLUR & SHARPEN RESTORATION: Actively deblur, sharpen, and restore all facial features, eyes, and skin texture into crisp, crystal-clear focus. No person should be left blurry. "
        "HYPER-REALISTIC SKIN TEXTURE (ZERO OVER-SMOOTHING): "
        "- Youthful, natural teenage skin texture with authentic micro-details, visible fine pores, subtle natural skin creases, healthy balanced complexion without heavy makeup or artificial smoothing. "
        "CLOTHING & UNIFORM: "
        "- Neat, stylish, realistic Korean-style high school uniform appropriate for gender (clean tailored blazer jacket, crisp collared shirt, and school tie/ribbon) with realistic fabric textures and natural folds. "
        "SEAMLESS STUDIO BACKDROP & THREE-POINT LIGHTING (ZERO OPTICAL BLUR): "
        "- Background is a completely clean, solid, seamless photography studio cyclorama wall in subtle elegant light-gray and soft beige tones. "
        "- ABSOLUTELY ZERO OPTICAL BLUR, ZERO BOKEH, NO SHALLOW DEPTH OF FIELD. Dimensional subject separation is achieved purely through directional studio key lighting, balanced ambient fill, natural catchlights in every pupil, and tonal contrast against the solid wall, NOT through lens blurring. "
        "STUDIO OPTICS & FULL PAN-FOCUS SPECIFICATIONS: "
        "- Professional studio camera, f/8 group portrait aperture, deep pan-focus across ALL subjects in the frame. "
        "- Uniform, razor-sharp optical focus across EVERY person from edge to edge without any out-of-focus areas. "
        "STRICT EXCLUSIONS & NEGATIVE CONSTRAINTS: "
        "plastic skin, porcelain doll face, airbrushed smoothness, heavy retouching, beauty filter, over-smoothed skin, generic anime/idol face, altered bone structure, CGI, 3D render, cartoon, digital painting, adult or child appearance, bokeh, shallow depth of field, background blur, out-of-focus blur, blurry background, artificial blurring, lens blur, selective focus blurring other people, out-of-focus background person, blurry secondary face, motion blur, partial blur on human bodies, depth-of-field blur on faces."
    ),
    3: (
        "Ultra-realistic studio portrait of the people in the input photograph transformed into dignified, realistic older adults, approximately 65–80 years old. "
        "CRITICAL MULTI-PERSON INDIVIDUAL SUBJECT PRESERVATION: "
        "- Preserve the exact number of people visible in the input image. Do not add, remove, duplicate, or merge anyone. "
        "- RECOGNIZE AND TREAT EVERY SINGLE PERSON AS AN INDEPENDENT PRIMARY SUBJECT: If there are multiple people (e.g. 2 or more people), every individual must be individually identified and transformed into their own aged counterpart with equal dignity, clarity, and detail. "
        "- Strictly preserve each person's recognizable facial bone structure, jawline, eye shape, eyelid folds, eyebrow structure, nose contour, and mouth shape from their respective face in the input photograph. "
        "- The elderly persons MUST be undeniably and recognizably the EXACT same individuals gracefully aged, preserving their unique facial identity and expressions. "
        "- If wearing glasses, preserve the exact glasses style, frame, and fit naturally on the aged face. "
        "- Strictly preserve each person's original pose, posture, head tilt, body angle, and hand gestures. "
        "- DEBLUR & SHARPEN RESTORATION: Actively deblur, sharpen, and restore all facial features, eyes, and skin texture into crisp, crystal-clear focus. No person should be left blurry. "
        "GRACEFUL NATURAL AGING & HYPER-REALISTIC SKIN TEXTURE: "
        "- Natural, authentic aging anchored to each subject's own facial structure: subtle laugh lines, fine crow's feet around eyes, natural forehead lines, realistic skin texture with visible pores and natural aged skin elasticity. "
        "- Dignified silver/gray hair with realistic hair strand texture and natural volume. Avoid grotesque deformities, excessive hollow cheeks, or extreme uncharacteristic wrinkles. "
        "CLOTHING & AMBIENCE: "
        "- Elegant, sophisticated, warm elderly knitwear or classic tailored blazer attire with authentic fabric texture. "
        "SEAMLESS STUDIO BACKDROP & THREE-POINT LIGHTING (ZERO OPTICAL BLUR): "
        "- Background is a completely clean, classic, solid seamless photography studio cyclorama wall with warm neutral studio lighting. "
        "- ABSOLUTELY ZERO OPTICAL BLUR, ZERO BOKEH, NO SHALLOW DEPTH OF FIELD. Dimensional subject separation is achieved purely through directional studio key lighting, balanced ambient fill, natural warm catchlights in every eye, and tonal contrast against the solid wall, NOT through lens blurring. "
        "STUDIO OPTICS & FULL PAN-FOCUS SPECIFICATIONS: "
        "- Professional studio camera, f/8 group portrait aperture, deep pan-focus across ALL subjects in the frame. "
        "- Uniform, razor-sharp optical focus across EVERY person from edge to edge without any out-of-focus areas. "
        "STRICT EXCLUSIONS & NEGATIVE CONSTRAINTS: "
        "plastic skin, porcelain face, airbrushed smoothness, heavy retouching, artificial mask, exaggerated grotesque wrinkles, hunchback, cartoon, caricature, CGI, 3D render, distortion, bokeh, shallow depth of field, background blur, out-of-focus blur, blurry background, artificial blurring, lens blur, selective focus blurring other people, out-of-focus background person, blurry secondary face, motion blur, partial blur on human bodies, depth-of-field blur on faces."
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
    
    # 1. 1024x1024 고화질 RGB 리사이즈
    img_square = image.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
    
    # 2. [선예도 강화 전처리: 언샵 마스크] 블러 없이 엣지 대비를 극대화하여 안면 디테일 쨍하게 전달
    img_enhanced = img_square.filter(ImageFilter.UnsharpMask(radius=1.5, percent=140, threshold=2))
    
    img_bytes = io.BytesIO()
    # 전송 속도 최적화를 위해 optimize=True 및 compress_level=4 적용 (네트워크 레이턴시 대폭 단축)
    img_enhanced.save(img_bytes, format="PNG", optimize=True, compress_level=4)
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


