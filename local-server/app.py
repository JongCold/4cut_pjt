"""
app.py
AI 4컷 포토부스 통합 FastAPI 백엔드 & Google Drive 연동 & APScheduler 데이터 자동 파기
"""

import os
import io
import re
import time
import uuid
import base64
import threading
from typing import List, Optional
from datetime import datetime, timedelta

from pydantic import BaseModel
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import qrcode
from apscheduler.schedulers.background import BackgroundScheduler

from concept_transformer import transform_four_cut, create_4cut_frame
from openai_transformer import transform_single_image_openai
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=10)
TRANSFORM_TASKS = {}
TRANSFORM_PROGRESS = {}

def set_progress(session_id: str, step: int, progress: int, step_name: str, message: str):
    """세션별 실시간 AI 변환 및 인화 진행률 갱신"""
    if session_id not in TRANSFORM_PROGRESS:
        TRANSFORM_PROGRESS[session_id] = {
            "start_time": time.time(),
            "step": 1,
            "progress": 5,
            "step_name": "촬영 초기화",
            "message": "AI 생애 주기 변환을 준비하고 있습니다..."
        }
    entry = TRANSFORM_PROGRESS[session_id]
    entry["step"] = step
    entry["progress"] = progress
    entry["step_name"] = step_name
    entry["message"] = message

# 기본 경로 및 폴더 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# .env 환경변수 파일 자동 로드
env_file_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_file_path):
    with open(env_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
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
    """구글 드라이브 파일 업로드 (GAS Webhook 재시도 및 Service Account Fallback 지원)"""
    import urllib.request
    import json
    
    folder_type = "video" if folder_id == GOOGLE_VIDEO_FOLDER_ID else "photo"

    # 1. Google Apps Script (GAS) Webhook 방식 우선 (사용자 5TB 할당량 사용)
    if GAS_WEBHOOK_URL:
        # 최대 2회 재시도
        for attempt in range(2):
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
                
                res = requests.post(GAS_WEBHOOK_URL, json=payload, headers=headers, timeout=60, allow_redirects=True)
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
                        print(f"[Google Drive GAS Error] 응답 파싱 실패 ({parse_err}).")
                elif res.status_code in (301, 302, 307, 308):
                    # 리다이렉트 발생 시 재시도
                    continue
                else:
                    print(f"[Google Drive GAS Error] GAS 업로드 실패 (HTTP {res.status_code}, 시도 {attempt+1}/2).")
            except Exception as ex:
                print(f"[Google Drive GAS Error] GAS 연동 예외 (시도 {attempt+1}/2): {ex}")
            time.sleep(1)

    # 2. Service Account API 방식 Fallback
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
            if "storageQuotaExceeded" in str(e) or "quota" in str(e).lower():
                print(f"[Google Drive] ℹ️ 서비스 계정 저장공간(0MB Quota) 정책 제한: GAS Webhook 설정을 확인해주세요. (파일은 로컬 'uploads/'에 안전하게 보관되어 모바일 즉시 다운로드 가능)")
            else:
                print(f"[Google Drive API] ⚠️ 업로드 실패: {e}")
            return None
    
    return None


def delete_session_files_after_delay(session_id: str, delay_seconds: int = 60):
    """
    모바일 다운로드 완료 알림 수신 시,
    사용자가 사진과 동영상을 모두 다운로드할 수 있도록 짧은 유예 시간(기본 60초) 후
    해당 세션과 관련된 로컬 uploads/ 내의 모든 파일(사진 4장, 원본 프레임, AI 프레임, 비디오)을 영구 삭제합니다.
    """
    def _worker():
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        
        deleted_count = 0
        try:
            if not os.path.exists(UPLOAD_DIR):
                return
            for fname in os.listdir(UPLOAD_DIR):
                if session_id in fname:
                    fpath = os.path.join(UPLOAD_DIR, fname)
                    if os.path.isfile(fpath):
                        try:
                            os.remove(fpath)
                            deleted_count += 1
                            print(f"[Instant Cleanup] 다운로드 완료에 따른 세션 파일 영구 파기: {fname}")
                        except Exception as e:
                            print(f"[Instant Cleanup Error] 파일 삭제 실패 ({fname}): {e}")
            if deleted_count > 0:
                print(f"[Instant Cleanup] ✅ 세션 '{session_id}' 파일 총 {deleted_count}개 영구 파기 완료")
        except Exception as ex:
            print(f"[Instant Cleanup Error] 세션 정리 오류: {ex}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


class CleanupSessionRequest(BaseModel):
    session_id: Optional[str] = None
    files: Optional[List[str]] = None
    delay_seconds: Optional[int] = 60
    immediate: Optional[bool] = False


def cleanup_expired_files():
    """24시간 이상 경과한 로컬 및 구글 드라이브 파일 자동 파기 (개인정보 보호 준수)"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 24시간 만료 데이터 자동 파기 검사 스케줄러 실행 중...")
    now = time.time()
    retention_period = 24 * 3600  # 24시간 (초)
    temp_retention_period = 1800  # 임시 파일 30분 초과 시 삭제
    
    # 1. 로컬 UPLOAD_DIR 파일 검사 및 영구 삭제
    local_deleted = 0
    if os.path.exists(UPLOAD_DIR):
        for fname in os.listdir(UPLOAD_DIR):
            fpath = os.path.join(UPLOAD_DIR, fname)
            if os.path.isfile(fpath):
                file_age = now - os.path.getmtime(fpath)
                # 24시간 지난 모든 파일 또는 30분 지난 임시(temp_) 파일 파기
                if file_age > retention_period or (fname.startswith("temp_") and file_age > temp_retention_period):
                    try:
                        os.remove(fpath)
                        local_deleted += 1
                        print(f"[Auto Cleanup] 만료된 로컬 파일 영구 파기: {fname}")
                    except Exception as e:
                        print(f"[Auto Cleanup Error] 로컬 파일 삭제 실패 ({fname}): {e}")
    if local_deleted > 0:
        print(f"[Auto Cleanup] ✅ 로컬 만료 파일 {local_deleted}개 영구 파기 완료")

    # 2. GAS Webhook을 통한 구글 드라이브 24시간 만료 파일 자동 파기 원격 호출
    if GAS_WEBHOOK_URL:
        try:
            import requests
            cleanup_payload = {"action": "cleanup"}
            res = requests.post(GAS_WEBHOOK_URL, json=cleanup_payload, timeout=30)
            if res.status_code == 200:
                print(f"[Auto Cleanup] ✅ Google Apps Script 클라우드 24시간 만료 파일 파기 동기화 완료")
        except Exception as ex:
            pass

    # 3. 서비스 계정이 직접 생성한 구글 드라이브 파일 검사 (Service Account 소유 파일 대상)
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
                        if "insufficientFilePermissions" in str(ex):
                            pass
                        else:
                            print(f"[Auto Cleanup Error] 구글 드라이브 파일 삭제 실패 ({f['id']}): {ex}")
            except Exception as e:
                pass


# APScheduler 가동 (15분마다 검사 및 서버 시작 시 즉시 실행)
scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_expired_files, "interval", minutes=15)
scheduler.start()

# 서버 시작 시 24시간 지난 만료 파일 즉시 파기 실행
try:
    cleanup_expired_files()
except Exception as e:
    print(f"[Auto Cleanup] 초기 파기 실패: {e}")


@app.post("/api/cleanup-session")
async def api_cleanup_session(req: CleanupSessionRequest):
    """
    QR 모바일 다운로드 후 자동 파기 엔드포인트
    - 모바일 브라우저에서 사진 또는 영상 다운로드 완료 시 호출됨
    - 기본 60초(사진과 영상을 모두 받을 수 있는 시간) 후 해당 세션의 로컬 파일 영구 파기
    """
    sid = req.session_id
    if not sid and req.files:
        for f in req.files:
            match = re.search(r"([a-f0-9]{8})", f)
            if match:
                sid = match.group(1)
                break
                
    if not sid:
        raise HTTPException(status_code=400, detail="session_id or valid files parameter is required")
        
    delay = 0 if req.immediate else (req.delay_seconds if req.delay_seconds is not None else 60)
    delete_session_files_after_delay(sid, delay_seconds=delay)
    
    return {
        "status": "success",
        "message": f"세션 '{sid}'의 모든 미디어 파일이 {delay}초 후 영구 파기되도록 예약되었습니다.",
        "session_id": sid,
        "scheduled_delay": delay
    }


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


def process_video_to_2x_mp4(input_path: str, output_path: str) -> bool:
    """
    webm 비디오 파일을 읽어서 2배속(속도 2배 빠르게, 재생시간 절반 감축)으로 MP4(H.264, iOS 호환)로 고속 변환 및 압축 저장
    imageio_ffmpeg 또는 시스템 ffmpeg가 없을 경우 원본 복사로 안전 fallback 처리
    """
    import subprocess
    import shutil
    
    # 1. imageio_ffmpeg 또는 시스템 ffmpeg 경로 탐색
    ffmpeg_exe = "ffmpeg"
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    try:
        cmd = [
            ffmpeg_exe,
            '-y',
            '-i', input_path,
            '-filter:v', 'setpts=0.5*PTS',
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-preset', 'fast',
            '-crf', '24',
            '-an',
            output_path
        ]
        res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"[Video Process] ✅ 비디오 2배속(빠르게) 변환 및 H.264 MP4 고속 인코딩 성공: {output_path}")
        return True
    except Exception as e:
        print(f"[Video Process Warning] ffmpeg 2배속 변환 불가 ({e}). 원본 파일로 안전하게 대체합니다.")
        try:
            shutil.copyfile(input_path, output_path)
            return True
        except Exception as copy_err:
            print(f"[Video Process Error] 파일 복사 실패: {copy_err}")
            return False


@app.get("/api/transform_status/{session_id}")
async def get_transform_status(session_id: str):
    """
    세션별 실시간 AI 변환 및 인화 진행 상태 조회 (프론트엔드 동적 프로그레스 UI 연동)
    """
    prog = TRANSFORM_PROGRESS.get(session_id)
    if not prog:
        return {
            "status": "waiting",
            "step": 1,
            "progress": 5,
            "step_name": "초기화 중",
            "message": "AI 생애 주기 변환을 준비하고 있습니다...",
            "elapsed_seconds": 0
        }
    
    elapsed = int(time.time() - prog.get("start_time", time.time()))
    return {
        "status": "completed" if prog.get("progress", 0) >= 100 else "processing",
        "step": prog.get("step", 1),
        "progress": prog.get("progress", 5),
        "step_name": prog.get("step_name", "진행 중"),
        "message": prog.get("message", ""),
        "elapsed_seconds": elapsed
    }


@app.post("/api/transform_single")
async def api_transform_single(
    session_id: str = Form(...),
    cut_index: int = Form(...),
    style: str = Form("time_travel"),
    is_high_quality: str = Form("false"),
    photo: UploadFile = File(...)
):
    """
    개별 사진 수신 후 즉시 백그라운드 변환 시작
    """
    if session_id not in TRANSFORM_TASKS:
        TRANSFORM_TASKS[session_id] = {}
        
    contents = await photo.read()
    pil_img = Image.open(io.BytesIO(contents))
    
    # 원본 이미지 저장
    single_filename = f"orig_single_{cut_index+1}_{session_id}.jpg"
    single_path = os.path.join(UPLOAD_DIR, single_filename)
    pil_img.save(single_path, format="JPEG", quality=95)
    
    # 모델 선택
    model_name = "gpt-image-2" if is_high_quality.lower() == "true" else "gpt-image-1.5"
    
    # 컷별 실시간 진행 상태 등록
    step_descriptions = {
        0: (1, 15, "1컷 유년기 변환", "어린이 AI 실사 변환 분석 중... (골격 100% 보존)"),
        1: (2, 35, "2컷 청소년기 변환", "청소년 교복 AI 실사 변환 분석 중..."),
        2: (3, 50, "3컷 현재 원본 보존", "현재 본연의 모습 원본 100% 보존 완료"),
        3: (4, 65, "4컷 노년기 변환", "품격 있는 황혼 AI 실사 변환 분석 중...")
    }
    step_num, prog_val, s_name, s_msg = step_descriptions.get(cut_index, (1, 10, "변환 진행 중", "AI 이미지 분석 중..."))
    set_progress(session_id, step_num, prog_val, s_name, s_msg)

    # 백그라운드 태스크 등록
    loop = asyncio.get_event_loop()
    if style == "original":
        task = loop.run_in_executor(executor, lambda img: img.convert("RGB"), pil_img)
    else:
        # time_travel (연령 변환) 및 기타 테마
        task = loop.run_in_executor(executor, transform_single_image_openai, pil_img, cut_index, model_name)
        
    TRANSFORM_TASKS[session_id][cut_index] = {
        "original_img": pil_img,
        "single_path": single_path,
        "single_filename": single_filename,
        "task": task
    }
    return {"status": "success", "style": style, "cut_index": cut_index}

def get_host_lan_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.post("/api/transform")
async def api_transform_four_cut(
    request: Request,
    session_id: str = Form(...),
    video: Optional[UploadFile] = File(None),
    style: str = Form("original")
):
    """
    4컷 촬영 완료 후 최종 병합 및 구글 드라이브 업로드
    """
    if session_id not in TRANSFORM_TASKS or len(TRANSFORM_TASKS[session_id]) < 4:
        raise HTTPException(status_code=400, detail="모든 4컷 사진이 전송되지 않았습니다.")

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    set_progress(session_id, 4, 70, "변환 마무리 대기", "생애 주기별 고화질 AI 이미지 변환 결과를 수집하고 있습니다...")

    # 1. 캡처된 원본 4장 수집 (async 태스크 대기)
    original_pil_images = []
    single_orig_filenames = []
    single_orig_paths = []
    transformed_pil_images = []
    
    cut_finish_msgs = {
        0: (1, 30, "1컷 유년기 완료", "어린이 AI 변환 완료 (DSLR 실사 텍스처 반영)"),
        1: (2, 55, "2컷 청소년기 완료", "청소년 교복 AI 변환 완료"),
        2: (3, 65, "3컷 현재 모습 완료", "현재 원본 보존 완료"),
        3: (4, 80, "4컷 노년기 완료", "노년 황혼 AI 변환 완료")
    }

    for idx in range(4):
        item = TRANSFORM_TASKS[session_id][idx]
        original_pil_images.append(item["original_img"])
        single_orig_filenames.append(item["single_filename"])
        single_orig_paths.append(item["single_path"])
        
        # AI 변환 완료 대기 (비동기 처리)
        transformed_img = await item["task"]
        transformed_pil_images.append(transformed_img)

        # 각 컷 변환 완료 시 실시간 상태 갱신
        s_num, s_prog, s_title, s_desc = cut_finish_msgs.get(idx, (idx+1, 20*(idx+1), "완료", "처리 중"))
        set_progress(session_id, s_num, s_prog, s_title, s_desc)
        
    # 메모리 정리
    del TRANSFORM_TASKS[session_id]
        
    # 2. 원본 4컷 프레임 합성 및 저장
    orig_frame = create_4cut_frame(original_pil_images, brand_title="AI 4-CUT STUDIO (ORIGINAL)")
    orig_frame_filename = f"orig_frame_{session_id}.jpg"
    orig_frame_path = os.path.join(UPLOAD_DIR, orig_frame_filename)
    orig_frame.save(orig_frame_path, format="JPEG", quality=92)
    
    # 3. AI 변환 적용 & 4컷 프레임 생성
    set_progress(session_id, 5, 85, "4컷 인화 프레임 렌더링", "고해상도 4컷 포토 프레임을 합성 중입니다...")
    frame_title = "AI 4-CUT (TIME TRAVEL)" if style == "time_travel" else f"AI 4-CUT STUDIO ({style.upper()})"
    ai_frame = create_4cut_frame(transformed_pil_images, brand_title=frame_title)
    ai_frame_filename = f"ai_frame_{session_id}_{style}.jpg"
    ai_frame_path = os.path.join(UPLOAD_DIR, ai_frame_filename)
    ai_frame.save(ai_frame_path, format="JPEG", quality=95)
    
    # 4. 비하인드 동영상 저장 (2배속 인코딩 및 H.264 MP4로 변환)
    set_progress(session_id, 5, 90, "2배속 비하인드 영상 인코딩", "촬영 순간을 담은 2배속 모바일 최적화 비디오를 생성 중입니다...")
    video_filename = f"behind_video_{session_id}.mp4"
    video_path = os.path.join(UPLOAD_DIR, video_filename)
    if video:
        v_contents = await video.read()
        temp_webm_path = os.path.join(UPLOAD_DIR, f"temp_{session_id}.webm")
        with open(temp_webm_path, "wb") as f:
            f.write(v_contents)
        
        # 2배속 MP4 변환 실행
        success = False
        if os.path.exists(temp_webm_path) and os.path.getsize(temp_webm_path) > 0:
            success = process_video_to_2x_mp4(temp_webm_path, video_path)
            
        # 임시 webm 파일 제거
        try:
            if os.path.exists(temp_webm_path):
                os.remove(temp_webm_path)
        except Exception:
            pass
            
        if not success:
            # 변환 실패 시 fallback으로 원본 그대로 저장
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

    # 5. 구글 드라이브 업로드 최적화
    set_progress(session_id, 5, 95, "클라우드 저장 및 QR 발급", "구글 드라이브 업로드 및 모바일 QR 코드를 생성하고 있습니다...")
    
    # 5-1. 필수 메인 결과물 (AI 4컷 프레임 + 비하인드 동영상) 우선 동기 업로드
    img_drive_id = upload_to_google_drive(ai_frame_path, ai_frame_filename, "image/jpeg", folder_id=GOOGLE_PHOTO_FOLDER_ID)
    vid_drive_id = upload_to_google_drive(video_path, video_filename, "video/mp4", folder_id=GOOGLE_VIDEO_FOLDER_ID)
    
    # 5-2. 개별 원본 사진 4장 및 원본 프레임은 백그라운드 스레드로 비동기 업로드 (대기시간 15초 대폭 단축)
    def _bg_upload_originals():
        for idx, s_path in enumerate(single_orig_paths):
            upload_to_google_drive(s_path, single_orig_filenames[idx], "image/jpeg", folder_id=GOOGLE_PHOTO_FOLDER_ID)
        upload_to_google_drive(orig_frame_path, orig_frame_filename, "image/jpeg", folder_id=GOOGLE_PHOTO_FOLDER_ID)
    
    executor.submit(_bg_upload_originals)
    
    img_param = img_drive_id if img_drive_id else ai_frame_filename
    vid_param = vid_drive_id if vid_drive_id else video_filename
    
    # 6. No-DB 모바일 1-클릭 즉시 다운로드 URL 및 Dynamic QR 생성 (스마트폰 직결 LAN IP 지원)
    lan_ip = get_host_lan_ip()
    port = request.base_url.port or 8000
    server_origin = f"http://{lan_ip}:{port}"
    
    download_url = f"{server_origin}/download.html?img={ai_frame_filename}&vid={video_filename}&sid={session_id}&srv={server_origin}&gid={img_drive_id or ''}&gvid={vid_drive_id or ''}"
    local_download_url = download_url
    
    # QR 코드 생성
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(download_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = io.BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode("utf-8")

    set_progress(session_id, 5, 100, "인화 및 완성 완료!", "모든 변환이 완료되었습니다. 결과 화면으로 이동합니다.")

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
        "drive_status_msg": "구글 드라이브 업로드 완료 (AI 프레임 및 비디오)" if (img_drive_id and vid_drive_id) else "로컬 스토리지 저장 완료 (24시간 자동 파기 대상)"
    }
