/**
 * Google Apps Script (GAS) - AI 4컷 포토부스 구글 드라이브 업로더 (v2.0)
 * 
 * [배포 방법 - 1분 소요]:
 * 1. https://script.google.com 접속 -> 기존 프로젝트 열기 (또는 '새 프로젝트')
 * 2. 아래 코드를 전체 붙여넣기 한 뒤 저장(Ctrl+S)
 * 3. 상단 [배포] -> [새 배포] 클릭 (또는 배포 관리에서 새 버전 배포)
 * 4. 유형: [웹 앱] 선택
 * 5. 다음 사용자 권한으로 실행: [나 (kjhkjh10114@gmail.com)]
 * 6. 액세스 권한이 있는 사용자: [모든 사용자 (Anyone)] 선택 후 [배포] 클릭
 * 7. 생성된 웹 앱 URL (https://script.google.com/macros/s/.../exec)을 확인합니다.
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

// POST 요청 처리 (사진 및 영상 구글 드라이브 자동 저장)
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "No post data received"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    const data = JSON.parse(e.postData.contents);
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
      // 지정 폴더 접근 실패 시 루트 폴더 사용
      folder = DriveApp.getRootFolder();
    }
    
    const decodedBlob = Utilities.newBlob(Utilities.base64Decode(base64Data), mimeType, filename);
    const file = folder.createFile(decodedBlob);
    
    // 누구나 다운로드/보기 가능하도록 공유 권한 부여
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
