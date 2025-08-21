from google.cloud import firestore
from google.cloud import storage

# --- Firestore and GCS Clients ---
db = firestore.Client()
storage_client = storage.Client()
VIDEO_COLLECTION = "videos"

def find_videos_to_delete():
    """削除対象の動画（両者ダウンロード済み）をFirestoreから検索する"""
    try:
        videos_ref = db.collection(VIDEO_COLLECTION)
        query = videos_ref.where("downloaded_by_main", "==", True).where("downloaded_by_sub", "==", True).where("deleted_from_gcs", "==", False)
        return query.stream()
    except Exception as e:
        print(f"Database query failed: {e}")
        return []

def delete_from_gcs(gcs_path):
    """GCSからファイルを削除する"""
    if not gcs_path:
        print("GCS path is missing, cannot delete.")
        return False
    try:
        blob = storage.Blob.from_string(gcs_path, client=storage_client)
        blob.delete()
        print(f"Successfully deleted {gcs_path} from GCS.")
        return True
    except Exception as e:
        print(f"Failed to delete {gcs_path} from GCS: {e}")
        return False

def mark_as_deleted_in_db(video_id):
    """Firestoreの削除ステータスを更新する"""
    try:
        doc_ref = db.collection(VIDEO_COLLECTION).document(video_id)
        doc_ref.update({"deleted_from_gcs": True})
        print(f"Marked video '{video_id}' as deleted in the database.")
    except Exception as e:
        print(f"Failed to update database for video '{video_id}': {e}")

if __name__ == "__main__":
    print("Starting cleanup process...")
    videos_to_delete = find_videos_to_delete()

    processed_count = 0
    for video_doc in videos_to_delete:
        processed_count += 1
        video_data = video_doc.to_dict()
        filename = video_data.get("filename")
        gcs_path_to_delete = video_data.get("gcs_path") # 元の動画を削除

        print(f"Processing '{filename}' for deletion...")

        if delete_from_gcs(gcs_path_to_delete):
            mark_as_deleted_in_db(video_doc.id)

    if processed_count == 0:
        print("No videos to delete at this time.")

    print("Cleanup process finished.")
