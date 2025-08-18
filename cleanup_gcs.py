import sqlite3
from google.cloud import storage

DB_NAME = "video_status.db"

def find_videos_to_delete():
    """削除対象の動画（両者ダウンロード済み）をデータベースから検索する"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # 両方のユーザーがダウンロード済みで、まだGCSから削除されていないファイルを選択
        cursor.execute(
            "SELECT id, filename, gcs_path FROM videos WHERE downloaded_by_main = 1 AND downloaded_by_sub = 1 AND deleted_from_gcs = 0"
        )
        videos = cursor.fetchall()
        conn.close()
        return videos
    except Exception as e:
        print(f"Database query failed: {e}")
        return []

def delete_from_gcs(gcs_path):
    """GCSからファイルを削除する"""
    try:
        storage_client = storage.Client()
        blob = storage.Blob.from_string(gcs_path, client=storage_client)
        blob.delete()
        print(f"Successfully deleted {gcs_path} from GCS.")
        return True
    except Exception as e:
        print(f"Failed to delete {gcs_path} from GCS: {e}")
        return False

def mark_as_deleted_in_db(video_id):
    """データベースの削除ステータスを更新する"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE videos SET deleted_from_gcs = 1 WHERE id = ?", (video_id,))
        conn.commit()
        conn.close()
        print(f"Marked video ID {video_id} as deleted in the database.")
    except Exception as e:
        print(f"Failed to update database for video ID {video_id}: {e}")

if __name__ == "__main__":
    print("Starting cleanup process...")
    videos_to_delete = find_videos_to_delete()

    if not videos_to_delete:
        print("No videos to delete at this time.")
    else:
        for video in videos_to_delete:
            video_id, filename, gcs_path = video
            print(f"Processing '{filename}' for deletion...")

            # GCSからファイルを削除
            if delete_from_gcs(gcs_path):
                # 成功した場合のみ、DBのステータスを更新
                mark_as_deleted_in_db(video_id)

    print("Cleanup process finished.")
