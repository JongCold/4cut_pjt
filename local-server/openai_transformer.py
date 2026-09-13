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

# 1. [인생 사계절] 연령 변환 프롬프트 (0: 유년기, 1: 청소년기, 2: 원본유지, 3: 노년기)
PROMPTS_TIME_TRAVEL = {
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

# 2. [조선 4컷] 신분 변신 프롬프트 (0: 왕, 1: 선비, 2: 보부상, 3: 노비)
# 2인 이상 다인원(커플, 친구, 가족) 촬영 시에도 단 한 사람도 현대 옷에 남겨지지 않고 100% 조선시대 인물로 개별 변환
PROMPTS_JOSEON = {
    0: (
        "Recreate this as ONE cohesive, naturally rendered photograph — not a composite or overlay. The people, clothing, and background must all share the same lighting, shadows, and photographic depth, as if photographed together in a single shot. "
        "Preserve the exact pose, expression, body orientation, and position of every person in the photo. "
        "Preserve each person's unique biological facial identity, bone structure, eye shape, nose, mouth, and skin tone. "
        "CRITICAL MULTI-PERSON TRANSFORMATION & INDEPENDENT SUBJECT RULE: "
        "- Recognize and treat EVERY SINGLE PERSON visible in the input image as an independent primary subject. "
        "- Do NOT add, remove, merge, duplicate, or omit anyone. Preserve the exact number of people from the input image. "
        "- ABSOLUTELY NO PERSON SHOULD BE LEFT IN MODERN CLOTHING: Every single person in the photo MUST be completely transformed into traditional Joseon royal court attire. Under no circumstances should any person remain in modern clothing (such as modern black tank tops, sleeveless shirts, t-shirts, straps, or modern casual wear). "
        "- GENDER & ROLE APPROPRIATE ROYAL COSTUMES FOR MULTIPLE PEOPLE: "
        "  * Male subjects: Transformed into a Joseon King or royal prince wearing the royal red dragon robe (gonryongpo) with gold dragon embroidery (hyungbae) on chest and shoulders, paired with the traditional black winged royal crown (ikseongwan). "
        "  * Female subjects: Transformed into a Joseon Queen or royal princess wearing an exquisite royal silk court hanbok / ceremonial robe (dangui or hwal-ot) in rich royal colors with fine gold embroidery, paired with a traditional royal court hairstyle (elegant braided bun with binyeo hairpin or cheopji). "
        "  * If multiple men or multiple women appear, dress all of them in appropriate dignified Joseon royal court garments. "
        "AUTHENTIC ROYAL HAIRSTYLE & HEADWEAR INTEGRATION: "
        "- For subjects wearing the ikseongwan crown: All hair, bangs, and side locks must be cleanly combed back, pulled up into a traditional topknot (sangtu), and tucked completely inside a black horsehair headband (manggeon) beneath the crown. Absolutely NO modern floppy bangs, NO loose unkempt side hair spilling out from under the crown. The forehead and eyebrows should be cleanly and handsomely revealed. "
        "- For female subjects: Hair restyled into an authentic elegant Joseon royal court coiffure with traditional hairpins, keeping hairline neat, regal, and free of modern unkempt locks. "
        "BACKGROUND & ENVIRONMENT: "
        "Setting: the royal throne hall (eojeon) of a Korean palace, with subjects positioned in front of the royal throne (yongsang) and the folding screen 'Irworobongdo' (Sun, Moon, and Five Peaks). Wooden palace pillars with traditional dancheong patterns. "
        "STYLE & ATMOSPHERE: "
        "Mood: dignified, solemn, and regal. Lighting: soft natural interior light unifying all subjects and background together. Render style: photorealistic, 8k resolution, real photography look, shot on a full-frame camera, 50mm lens, natural film grain. "
        "STRICT NEGATIVE CONSTRAINTS: "
        "No modern clothing on any person, no modern black tank tops, no sleeveless shirts, no modern casual clothing left untransformed, no modern floppy bangs spilling out from the crown, no composite or cutout look, no altered facial identities, no extra invented people, no panel borders."
    ),
    1: (
        "Recreate this as ONE cohesive, naturally rendered photograph — not a composite or overlay. The people, clothing, and background must all share the same lighting, shadows, and photographic depth, as if photographed together in a single shot. "
        "Preserve the exact pose, expression, body orientation, and position of every person in the photo. "
        "Preserve each person's unique biological facial identity, bone structure, eye shape, nose, mouth, and skin tone. "
        "CRITICAL MULTI-PERSON TRANSFORMATION & INDEPENDENT SUBJECT RULE: "
        "- Recognize and treat EVERY SINGLE PERSON visible in the input image as an independent primary subject. "
        "- Do NOT add, remove, merge, duplicate, or omit anyone. Preserve the exact number of people from the input image. "
        "- ABSOLUTELY NO PERSON SHOULD BE LEFT IN MODERN CLOTHING: Every single person in the photo MUST be completely transformed into traditional Joseon noble/aristocratic (Yangban) attire. Under no circumstances should any person remain in modern clothing (such as modern black tank tops, sleeveless shirts, t-shirts, straps, or modern casual wear). "
        "- GENDER & ROLE APPROPRIATE NOBLE COSTUMES FOR MULTIPLE PEOPLE: "
        "  * Male subjects: Transformed into Joseon scholars wearing the flowing traditional scholar's outer robe (dopo) in ivory, white, or soft gray with a front tie sash (goreum), paired with the solid black horsehair hat (gat). "
        "  * Female subjects: Transformed into noble Joseon ladies (Yangban aristocratic women) wearing elegant high-class traditional hanbok made of fine silk or ramie (graceful jeogori jacket and voluminous full skirt chima in tasteful pastel or jewel tones), with neatly styled traditional hair (braided daenggi or elegant bun with hairpin). "
        "  * If multiple men or multiple women appear, dress all of them in appropriate noble Joseon aristocratic attire. "
        "AUTHENTIC NOBLE HAIRSTYLE & GAT INTEGRATION: "
        "- For subjects wearing the gat: All hair, front bangs, and side locks must be cleanly combed back, pulled up into an authentic topknot (sangtu), and tucked completely inside a black horsehair headband (manggeon) beneath the hat. Absolutely NO modern bangs falling onto the forehead, NO long sideburns, and NO messy wavy hair strands billowing out from beneath the brim of the gat. The forehead and eyebrows must be cleanly visible through the translucent mesh. "
        "- For female subjects: Hair neatly combed back and styled into an authentic elegant noblewoman's coiffure, with a neat hairline. "
        "BACKGROUND & ENVIRONMENT: "
        "Setting: a traditional Korean hanok house courtyard or wooden veranda (daecheong), with tiled roofs, wooden pillars, paper-latticed sliding doors (hanji windows), stone pathway, and scholarly atmosphere. "
        "STYLE & ATMOSPHERE: "
        "Mood: calm, refined, and scholarly. Lighting: soft natural daylight unifying all subjects and background. Render style: photorealistic, 8k resolution, real photography look, shot on a full-frame camera, 50mm lens, natural film grain. "
        "STRICT NEGATIVE CONSTRAINTS: "
        "No modern clothing on any person, no modern black tank tops, no sleeveless shirts, no modern casual clothing left untransformed, no modern floppy bangs hanging down from the gat, the gat must be solid black only, no composite or cutout look, no altered facial identities."
    ),
    2: (
        "Recreate this as ONE cohesive, naturally rendered photograph — not a composite or overlay. The people, clothing, and background must all share the same lighting, shadows, and photographic depth, as if photographed together in a single shot. "
        "Preserve the exact pose, expression, body orientation, and position of every person in the photo. "
        "Preserve each person's unique biological facial identity, bone structure, eye shape, nose, mouth, and skin tone. "
        "CRITICAL MULTI-PERSON TRANSFORMATION & INDEPENDENT SUBJECT RULE: "
        "- Recognize and treat EVERY SINGLE PERSON visible in the input image as an independent primary subject. "
        "- Do NOT add, remove, merge, duplicate, or omit anyone. Preserve the exact number of people from the input image. "
        "- ABSOLUTELY NO PERSON SHOULD BE LEFT IN MODERN CLOTHING: Every single person in the photo MUST be completely transformed into traditional Joseon peddler-merchant (bobusang) or market merchant attire. Under no circumstances should any person remain in modern clothing (such as modern black tank tops, sleeveless shirts, t-shirts, or casual wear). "
        "- PEDDLER COSTUMES FOR MULTIPLE PEOPLE: "
        "  * All subjects (male and female) wear simple traditional merchant work clothes (jeogori jacket and baji pants or working chima skirt) in plain durable cotton, worn and practical looking. "
        "  * Equipped with traditional merchant accessories: yellow bamboo straw hats (paengnyi) with white cotton tufts (somtteong) on both sides near the ears, and/or cloth bundle packs (bottjim) or wooden pack frames (jige) carried on the back. "
        "  * Hair must be neatly tied back and secured beneath headbands or hats, so that NO modern bangs or messy hair spill over the eyes. "
        "BACKGROUND & ENVIRONMENT: "
        "Setting: a traditional Korean countryside road or old marketplace (jang-teo), with dirt paths, thatched houses, wooden market stalls, and rustic rural scenery. "
        "STYLE & ATMOSPHERE: "
        "Mood: warm, humble, and hardworking. Lighting: soft natural daylight illuminating all subjects together. Render style: photorealistic, 8k resolution, real photography look, shot on a full-frame camera, 50mm lens. "
        "STRICT NEGATIVE CONSTRAINTS: "
        "No modern clothing on any person, no modern tank tops, no sleeveless shirts, no untransformed modern people, the straw hat must have white cotton tufts on both sides, no composite look, no altered facial identities."
    ),
    3: (
        "Recreate this as ONE cohesive, naturally rendered photograph — not a composite or overlay. The people, clothing, and background must all share the same lighting, shadows, and photographic depth, as if photographed together in a single shot. "
        "Preserve the exact pose, expression, body orientation, and position of every person in the photo. "
        "Preserve each person's unique biological facial identity, bone structure, eye shape, nose, mouth, and skin tone. "
        "CRITICAL MULTI-PERSON TRANSFORMATION & INDEPENDENT SUBJECT RULE: "
        "- Recognize and treat EVERY SINGLE PERSON visible in the input image as an independent primary subject. "
        "- Do NOT add, remove, merge, duplicate, or omit anyone. Preserve the exact number of people from the input image. "
        "- ABSOLUTELY NO PERSON SHOULD BE LEFT IN MODERN CLOTHING: Every single person in the photo MUST be completely transformed into worn, humble traditional Korean commoner/servant (nobi) hanbok. Under no circumstances should any person remain in modern clothing (such as modern black tank tops, sleeveless shirts, t-shirts, or casual wear). "
        "- SERVANT COSTUMES FOR MULTIPLE PEOPLE: "
        "  * All subjects (male and female) wear coarse, worn, plain white or off-white cotton/hemp fabric clothes with visible wrinkles, faded spots, and frayed edges (simple jeogori top with baji pants or humble skirt). "
        "  * Tie a plain white cloth headband (meoritti) around the forehead, and restyle the hair into a neat low bun (ttongmeori) at the nape of the neck. "
        "BACKGROUND & ENVIRONMENT: "
        "Setting: a traditional Korean thatched-roof house (chogajip) — straw roof, mud walls, simple dirt yard, wooden fence, earthenware jars (hangari), and rustic rural surroundings. "
        "STYLE & ATMOSPHERE: "
        "Mood: humble, weary, modest, and grounded. Lighting: soft, slightly muted natural daylight. Render style: photorealistic, 8k resolution, real photography look, shot on a full-frame camera, 50mm lens. "
        "STRICT NEGATIVE CONSTRAINTS: "
        "No modern clothing on any person, no modern tank tops, no sleeveless shirts, clothing must look worn and humble (not clean or luxurious), no untransformed people, no composite look, no altered facial identities."
    )
}

def transform_single_image_openai(
    image: Image.Image,
    cut_index: int,
    style: str = "time_travel",
    sub_theme: str = "",
    model_name: str = "gpt-image-2"
) -> Image.Image:
    """
    단일 이미지를 받아 OpenAI Edit API(Image-to-Image)를 통해 원본 얼굴/포즈 기반 고화질 변환을 수행합니다.
    - style: 'joseon' 또는 sub_theme == 'joseon' -> 조선시대 4색 신분 변신 (0:왕, 1:선비, 2:보부상, 3:노비)
    - style: 'time_travel' -> 인생 사계절 연령 변환 (0:유년기, 1:청소년기, 2:현재원본유지, 3:노년기)
    - model_name: 'gpt-image-2' 기본 탑재 (고화질 디폴트)
    """
    # 1. 테마에 따른 프롬프트 선택
    is_joseon = (style == "joseon" or sub_theme == "joseon")

    if is_joseon:
        prompt = PROMPTS_JOSEON.get(cut_index, "")
    else:
        # 인생 사계절 (3번째 컷은 현재 본연의 모습 100% 원본 유지)
        if cut_index == 2:
            return image.convert("RGB")
        prompt = PROMPTS_TIME_TRAVEL.get(cut_index, "")

    if not prompt:
        return image.convert("RGB")

    # 2. 1024x1024 고화질 RGB 리사이즈 (정방형 캔버스)
    img_square = image.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
    
    # 3. [선예도 강화 전처리: 언샵 마스크] 블러 없이 엣지 대비를 극대화하여 안면 디테일 쨍하게 전달
    img_enhanced = img_square.filter(ImageFilter.UnsharpMask(radius=1.5, percent=140, threshold=2))
    
    img_bytes = io.BytesIO()
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

    # 기본 모델: gpt-image-2 (고화질 기본 탑재)
    actual_model = model_name if model_name else "gpt-image-2"

    try:
        response = client.images.edit(
            model=actual_model,
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
            print(f"[OpenAI API Error] 조직 인증(Organization Verification)이 필요합니다.")
        else:
            print(f"[OpenAI API Error] Cut {cut_index} (Model: {actual_model}, Style: {style}): {e}")
        return image.convert("RGB")
