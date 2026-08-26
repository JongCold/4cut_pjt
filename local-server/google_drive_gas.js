/**
 * Google Apps Script (GAS) - AI 4컷 포토부스 구글 드라이브 업로더 & 자동 파기 (v2.2)
 * 
 * [배포 방법 - 1분 소요]:
 * 1. https://script.google.com 접속 -> 기존 프로젝트 열기 (또는 '새 프로젝트')
 * 2. 아래 코드를 전체 붙여넣기 한 뒤 저장(Ctrl+S)
 * 3. 상단 [배포] -> [새 배포] 클릭 (또는 배포 관리에서 새 버전 배포)
 * 4. 유형: [웹 앱] 선택
 * 5. 다음 사용자 권한으로 실행: [나 (kjhkjh10114@gmail.com)]
 * 6. 액세스 권한이 있는 사용자: [모든 사용자 (Anyone)] 선택 후 [배포] 클릭
 * 7. 생성된 웹 앱 URL (https://script.google.com/macros/s/.../exec)을 확인합니다.
 * 
 * [★ 24시간 자동 파기 트리거 등록 방법 - 개인정보 보호]:
 * 1. 구글 앱스 스크립트 편집기 왼쪽 메뉴에서 시계 아이콘(트리거 ⏰) 클릭.
 * 2. 오른쪽 하단 [+ 트리거 추가] 클릭.
 * 3. 실행할 함수 선택: [cleanupOldFiles] 선택.
 * 4. 이벤트 소스 선택: [시간 기반] 선택.
 * 5. 시간 기반 트리거 유형 선택: [시간 단위 타이머] 또는 [분 단위 타이머] 선택.
 * 6. 시간 간격 선택: [매시간] 또는 [15분마다] 선택 후 [저장] 클릭.
 * -> 이렇게 설정해두면 로컬 포토부스 PC가 꺼져있어도 구글 클라우드가 24시간 지난 사진/영상을 자동으로 영구 파기합니다.
 */

const PHOTO_FOLDER_ID = "13KXZ_W7vurFPHbC_1tImac7ZLBlRuS3Q";
const VIDEO_FOLDER_ID = "1RgvKVq-J7JItVRD6M_9asnU8NfnaQ_dU";

// GET 요청 헬스체크 및 302 리디렉션 응답 보장
function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({
    status: "success",
    message: "AI 4-Cut Studio Google Drive GAS Webhook Service Online"
  })).setMimeType(ContentService.MimeType.JSON);
}

// POST 요청 처리 (사진 및 영상 구글 드라이브 자동 저장 & 자동 파기 명령)
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "No post data received"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    const data = JSON.parse(e.postData.contents);
    
    // 1. 백엔드에서 자동 파기 트리거 호출 시
    if (data.action === "cleanup") {
      const cleanupResult = cleanupOldFiles();
      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        message: "Cleanup completed",
        result: cleanupResult
      })).setMimeType(ContentService.MimeType.JSON);
    }
    
    // 2. 사진/영상 파일 업로드 처리
    const filename = data.filename || "upload_file";
    const mimeType = data.mimeType || "image/jpeg";
    const base64Data = data.base64Data;
    const folderType = data.folderType; // 'photo' or 'video'
    
    if (!base64Data) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "Missing base64Data parameter"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    const targetFolderId = (folderType === 'video') ? VIDEO_FOLDER_ID : PHOTO_FOLDER_ID;
    let folder;
    
    try {
      folder = DriveApp.getFolderById(targetFolderId);
    } catch (fErr) {
      folder = DriveApp.getRootFolder();
    }
    
    const decodedBlob = Utilities.newBlob(Utilities.base64Decode(base64Data), mimeType, filename);
    const file = folder.createFile(decodedBlob);
    
    try {
      file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    } catch (sErr) {
      // 권한 세팅 예외 무시
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      fileId: file.getId(),
      downloadUrl: file.getDownloadUrl(),
      viewUrl: file.getUrl()
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

// [24시간 자동 파기 핵심 소스코드] 24시간 이상 지난 구글 드라이브 파일 휴지통으로 이동
function cleanupOldFiles() {
  const targetFolders = [PHOTO_FOLDER_ID, VIDEO_FOLDER_ID];
  const cutoffTime = new Date(Date.now() - 24 * 60 * 60 * 1000); // 현재 시간 기준 24시간 전
  let totalDeleted = 0;
  
  targetFolders.forEach(function(folderId) {
    try {
      const folder = DriveApp.getFolderById(folderId);
      const files = folder.getFiles();
      let count = 0;
      
      while (files.hasNext()) {
        const file = files.next();
        // 파일 생성 날짜가 24시간 이전인 경우
        if (file.getDateCreated() < cutoffTime) {
          file.setTrashed(true); // 휴지통으로 이동 (소유자 계정 권한으로 안전하게 삭제)
          count++;
          totalDeleted++;
        }
      }
      Logger.log("[Auto Cleanup] Folder ID " + folderId + ": Trashed " + count + " expired files.");
    } catch (e) {
      Logger.log("[Auto Cleanup Error] Folder ID " + folderId + " failed: " + e.toString());
    }
  });
  
  return { totalDeleted: totalDeleted };
}
