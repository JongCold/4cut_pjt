/**
 * Google Apps Script (GAS) - AI 4컷 포토부스 구글 드라이브 업로더
 * 
 * [배포 방법 - 1분 소요]:
 * 1. https://script.google.com 접속 -> '새 프로젝트' 클릭
 * 2. 아래 코드를 붙여넣기 후 상단 [배포] -> [새 배포] 클릭
 * 3. 유형: [웹 앱] 선택
 * 4. 다음 사용자 권한으로 실행: [나 (kjhkjh10114@gmail.com)]
 * 5. 액세스 권한이 있는 사용자: [모든 사용자 (Anyone)] 선택 후 [배포] 클릭
 * 6. 생성된 '웹 앱 URL' (https://script.google.com/macros/s/.../exec)을 복사하여 
 *    local-server/app.py의 GAS_WEBHOOK_URL 변수에 입력하면 구글 드라이브 100% 자동 업로드 연동 완료!
 */

const PHOTO_FOLDER_ID = "13KXZ_W7vurFPHbC_1tImac7ZLBlRuS3Q";
const VIDEO_FOLDER_ID = "1RgvKVq-J7JItVRD6M_9asnU8NfnaQ_dU";

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const filename = data.filename;
    const mimeType = data.mimeType;
    const base64Data = data.base64Data;
    const folderType = data.folderType; // 'photo' or 'video'
    
    const targetFolderId = (folderType === 'video') ? VIDEO_FOLDER_ID : PHOTO_FOLDER_ID;
    const folder = DriveApp.getFolderById(targetFolderId);
    
    const decodedBlob = Utilities.newBlob(Utilities.base64Decode(base64Data), mimeType, filename);
    const file = folder.createFile(decodedBlob);
    
    // 공개 읽기 권한 부여
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    
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
