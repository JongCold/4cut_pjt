"""
app.py
AI 4컷 포토부스 통합 FastAPI 백엔드 & Google Drive 연동 & APScheduler 데이터 자동 파기
"""

import os
import io
import time
import uuid
import base64
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import qrcode
from apscheduler.schedulers.background import BackgroundScheduler

from concept_transformer import transform_four_cut, create_4cut_frame

# 기본 경로 및 폴더 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
VERCEL_DIR = os.path.join(os.path.dirname(BASE_DIR), "vercel-frontend")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Google Drive API 지정 폴더 ID 및 인증 파일 경로 (사진 / 영상 저장소 분리)
GOOGLE_PHOTO_FOLDER_ID = "13KXZ_W7vurFPHbC_1tImac7ZLBlRuS3Q"
GOOGLE_VIDEO_FOLDER_ID = "1RgvKVq-J7JItVRD6M_9asnU8NfnaQ_dU"
GOOGLE_KEY_PATH = os.path.join(BASE_DIR, "google-key.json")
GAS_WEBHOOK_URL = os.environ.get("GAS_WEBHOOK_URL", "https://script.google.com/macros/s/AKfycbw1b3onN_ZUkYEI816LMT8XGV-Dl9EpHkZEjkplPaIA6L-YZSGTuGmYBcEitU6yK5N1/exec")  # Google Apps Script Webhook URL

DRIVE_SERVICE = None

# 구글 드라이브 API 인증 초기화 시도
try:
    if os.path.exists(GOOGLE_KEY_PATH):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        
        SCOPES = ["https://www.googleapis.com/auth/drive"]
        creds = service_account.Credentials.from_service_account_file(GOOGLE_KEY_PATH, scopes=SCOPES)
        DRIVE_SERVICE = build("drive", "v3", credentials=creds)
        print(f"[Google Drive API] ✅ 인증 성공! (사진 폴더: {GOOGLE_PHOTO_FOLDER_ID}, 영상 폴더: {GOOGLE_VIDEO_FOLDER_ID})")
    else:
        print(f"[Google Drive API] ⚠️ '{GOOGLE_KEY_PATH}' 인증 파일이 존재하지 않습니다. 로컬 Fallback 모드로 동작하며 드라이브 업로드가 건너뛰어집니다.")
except Exception as e:
    print(f"[Google Drive API] ❌ 연동 초기화 오류 ({e}). 로컬 Fallback 스토리지 모드로 연동됩니다.")

# FastAPI 앱 생성
app = FastAPI(title="AI 4-Cut Studio Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/templates", StaticFiles(directory=TEMPLATES_DIR), name="templates")
if os.path.exists(VERCEL_DIR):
    app.mount("/vercel", StaticFiles(directory=VERCEL_DIR), name="vercel")


def upload_to_google_drive(file_path: str, filename: str, mime_type: str, folder_id: str = None) -> Optional[str]:
    """구글 드라이브 파일 업로드 (GAS Webhook 또는 Service Account 지원)"""
    import urllib.request
    import json
    
    folder_type = "video" if folder_id == GOOGLE_VIDEO_FOLDER_ID else "photo"

    # 1. Google Apps Script (GAS) Webhook 방식 우선 (사용자 5TB 할당량 사용)
    if GAS_WEBHOOK_URL:
        try:
            import requests
            with open(file_path, "rb") as f:
                b64_content = base64.b64encode(f.read()).decode("utf-8")
            
            payload = {
                "filename": filename,
                "mimeType": mime_type,
                "base64Data": b64_content,
                "folderType": folder_type
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Content-Type": "application/json"
            }
            
            res = requests.post(GAS_WEBHOOK_URL, json=payload, headers=headers, timeout=60)
            if res.status_code == 200:
                try:
                    res_data = res.json()
                    if res_data.get("status") == "success":
                        file_id = res_data.get("fileId")
                        print(f"[Google Drive GAS] ✅ 구글 드라이브 업로드 성공! ID: {file_id}")
                        return file_id
                    else:
                        print(f"[Google Drive GAS Error] 스크립트 오류: {res_data.get('message')}")
                except Exception as parse_err:
                    print(f"[Google Drive GAS Error] 응답 파싱 실패 ({parse_err}). GAS 배포 설정을 '모든 사용자(Anyone)'로 지정했는지 확인하세요.")
            else:
                print(f"[Google Drive GAS Error] GAS 업로드 실패 (HTTP {res.status_code}). GAS 앱스 스크립트 배포 시 액세스 권한을 '모든 사용자(Anyone)'로 설정했는지 확인하세요.")
        except Exception as ex:
            print(f"[Google Drive GAS Error] GAS 연동 예외: {ex}")

    # 2. Service Account API 방식
    if DRIVE_SERVICE is not None:
        target_folder_id = folder_id if folder_id else GOOGLE_PHOTO_FOLDER_ID
        try:
            from googleapiclient.http import MediaFileUpload
            file_metadata = {
                "name": filename,
                "parents": [target_folder_id]
            }
            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
            file_obj = DRIVE_SERVICE.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink, webContentLink",
                supportsAllDrives=True
            ).execute()
            
            file_id = file_obj.get("id")
            DRIVE_SERVICE.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True
            ).execute()
            
            print(f"[Google Drive API] ✅ 서비스계정 업로드 성공: {filename} (ID: {file_id})")
            return file_id
        except Exception as e:
            print(f"[Google Drive API] ⚠️ 업로드 실패 (Service Account Quota 정책 제한): {e}")
            return None
    
    return None


def cleanup_expired_files():
    """24시간 이상 경과한 로컬 및 구글 드라이브 파일 자동 파기 (개인정보 보호 준수)"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 24시간 만료 데이터 자동 파기 검사 스케줄러 실행 중...")
    now = time.time()
    retention_period = 24 * 3600  # 24시간 (초)
    
    # 1. 로컬 UPLOAD_DIR 파일 검사
    for fname in os.listdir(UPLOAD_DIR):
        fpath = os.path.join(UPLOAD_DIR, fname)
        if os.path.isfile(fpath):
            file_age = now - os.path.getmtime(fpath)
            if file_age > retention_period:
                try:
                    os.remove(fpath)
                    print(f"[Auto Cleanup] 만료된 로컬 파일 영구 파기: {fname}")
                except Exception as e:
                    print(f"[Auto Cleanup Error] 로컬 파일 삭제 실패 ({fname}): {e}")

    # 2. 구글 드라이브 파일 검사 (사진 및 영상 폴더 모두 검사)
    if DRIVE_SERVICE is not None:
        cutoff_time = (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z"
        target_folders = [GOOGLE_PHOTO_FOLDER_ID, GOOGLE_VIDEO_FOLDER_ID]
        
        for folder_id in target_folders:
            try:
                query = f"'{folder_id}' in parents and createdTime < '{cutoff_time}' and trashed = false"
                results = DRIVE_SERVICE.files().list(q=query, fields="files(id, name, createdTime)").execute()
                files = results.get("files", [])
                for f in files:
                    try:
                        DRIVE_SERVICE.files().delete(fileId=f["id"]).execute()
                        print(f"[Auto Cleanup] 구글 드라이브 만료 파일 삭제 완료: {f['name']} (ID: {f['id']})")
                    except Exception as ex:
                        print(f"[Auto Cleanup Error] 구글 드라이브 파일 삭제 실패 ({f['id']}): {ex}")
            except Exception as e:
                print(f"[Auto Cleanup Error] 구글 드라이브 조회 실패 (Folder: {folder_id}): {e}")


# APScheduler 가동 (15분마다 검사 및 서버 시작 시 즉시 실행)
scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_expired_files, "interval", minutes=15)
scheduler.start()

# 서버 시작 시 24시간 지난 만료 파일 즉시 파기 실행
try:
    cleanup_expired_files()
except Exception as e:
    print(f"[Auto Cleanup] 초기 파기 실패: {e}")


@app.get("/", response_class=HTMLResponse)
async def serve_kiosk_home():
    """태블릿 패드 키오스크 메인 페이지 (`templates/index.html`)"""
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>AI 4-Cut Studio</h1><p>index.html 준비 중</p>")


@app.get("/download.html", response_class=HTMLResponse)
async def serve_download_viewer():
    """Vercel No-DB 모바일 다운로드 뷰어 페이지"""
    download_path = os.path.join(VERCEL_DIR, "download.html")
    if os.path.exists(download_path):
        with open(download_path, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>AI 4-Cut Studio Download Viewer</h1>")


@app.post("/api/transform")
async def api_transform_four_cut(
    request: Request,
    photos: List[UploadFile] = File(...),
    video: Optional[UploadFile] = File(None),
    style: str = Form("original")
):
    """
    4컷 사진 + 비하인드 동영상 수신 후:
    1. AI Img2Img 변환 & 4컷 합성 프레임 생성
    2. Google Drive API 업로드
    3. No-DB 모바일 뷰어 다운로드 QR 생성 및 반환
    """
    if len(photos) < 4:
        raise HTTPException(status_code=400, detail="사진은 정확히 4장이 전달되어야 합니다.")

    session_id = uuid.uuid4().hex[:8]
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. 캡처된 사진 4장 읽기 및 개별 원본 이미지 저장
    original_pil_images = []
    single_orig_filenames = []
    single_orig_paths = []
    
    for idx, photo in enumerate(photos[:4]):
        contents = await photo.read()
        pil_img = Image.open(io.BytesIO(contents))
        original_pil_images.append(pil_img)
        
        # 개별 원본 컷 이미지 로컬 저장 (24시간 자동 파기 대상)
        single_filename = f"orig_single_{idx+1}_{session_id}.jpg"
        single_path = os.path.join(UPLOAD_DIR, single_filename)
        pil_img.save(single_path, format="JPEG", quality=95)
        single_orig_filenames.append(single_filename)
        single_orig_paths.append(single_path)
        
    # 2. 원본 4컷 프레임 합성 및 저장
    orig_frame = create_4cut_frame(original_pil_images, brand_title="AI 4-CUT STUDIO (ORIGINAL)")
    orig_frame_filename = f"orig_frame_{session_id}.jpg"
    orig_frame_path = os.path.join(UPLOAD_DIR, orig_frame_filename)
    orig_frame.save(orig_frame_path, format="JPEG", quality=92)
    
    # 3. AI 변환 적용 & 4컷 프레임 생성
    transformed_pil_images = transform_four_cut(original_pil_images, style)
    ai_frame = create_4cut_frame(transformed_pil_images, brand_title=f"AI 4-CUT STUDIO ({style.upper()})")
    ai_frame_filename = f"ai_frame_{session_id}_{style}.jpg"
    ai_frame_path = os.path.join(UPLOAD_DIR, ai_frame_filename)
    ai_frame.save(ai_frame_path, format="JPEG", quality=95)
    
    # 4. 비하인드 동영상 저장
    video_filename = f"behind_video_{session_id}.webm"
    video_path = os.path.join(UPLOAD_DIR, video_filename)
    if video:
        v_contents = await video.read()
        with open(video_path, "wb") as f:
            f.write(v_contents)
    else:
        # 더미 파일 생성
        with open(video_path, "wb") as f:
            f.write(b"dummy_video_stream")

    # Base64 이미지 데이터 생성 (ngrok 경고 페이지 우회 및 초고속 즉시 렌더링)
    orig_buf = io.BytesIO()
    orig_frame.save(orig_buf, format="JPEG", quality=90)
    orig_frame_base64 = "data:image/jpeg;base64," + base64.b64encode(orig_buf.getvalue()).decode("utf-8")

    ai_buf = io.BytesIO()
    ai_frame.save(ai_buf, format="JPEG", quality=92)
    ai_frame_base64 = "data:image/jpeg;base64," + base64.b64encode(ai_buf.getvalue()).decode("utf-8")

    # 5. 구글 드라이브 업로드 (개별 원본 4장 + 원본 4컷 프레임 + AI 4컷 프레임 + 비하인드 동영상)
    for idx, s_path in enumerate(single_orig_paths):
        upload_to_google_drive(s_path, single_orig_filenames[idx], "image/jpeg", folder_id=GOOGLE_PHOTO_FOLDER_ID)

    upload_to_google_drive(orig_frame_path, orig_frame_filename, "image/jpeg", folder_id=GOOGLE_PHOTO_FOLDER_ID)
    img_drive_id = upload_to_google_drive(ai_frame_path, ai_frame_filename, "image/jpeg", folder_id=GOOGLE_PHOTO_FOLDER_ID)
    vid_drive_id = upload_to_google_drive(video_path, video_filename, "video/webm", folder_id=GOOGLE_VIDEO_FOLDER_ID)
    
    # Drive ID가 없는 경우 로컬 파일명 활용
    img_param = img_drive_id if img_drive_id else ai_frame_filename
    vid_param = vid_drive_id if vid_drive_id else video_filename
    
    # 6. No-DB 모바일 다운로드 URL 및 Dynamic QR 생성
    base_host = "https://4cut-pjt.vercel.app"
    server_origin = str(request.base_url).rstrip("/")
    download_url = f"{base_host}/download.html?img={img_param}&vid={vid_param}&srv={server_origin}"
    
    # 로컬 서빙 뷰어 URL 생성 (테스트용)
    local_download_url = f"http://localhost:8000/download.html?img={img_param}&vid={vid_param}&srv={server_origin}"
    
    # QR 코드 생성
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(download_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = io.BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode("utf-8")

    return {
        "status": "success",
        "session_id": session_id,
        "style": style,
        "ai_frame_url": f"/uploads/{ai_frame_filename}",
        "orig_frame_url": f"/uploads/{orig_frame_filename}",
        "single_orig_urls": [f"/uploads/{fn}" for fn in single_orig_filenames],
        "ai_frame_base64": ai_frame_base64,
        "orig_frame_base64": orig_frame_base64,
        "video_url": f"/uploads/{video_filename}",
        "image_file_id": img_param,
        "video_file_id": vid_param,
        "download_url": download_url,
        "local_download_url": local_download_url,
        "qr_code_base64": qr_base64,
        "drive_upload_success": img_drive_id is not None and vid_drive_id is not None,
        "drive_status_msg": "구글 드라이브 업로드 완료 (개별 원본 4장 포함)" if (img_drive_id and vid_drive_id) else "로컬 스토리지 저장 완료 (24시간 자동 파기 대상)"
    }
