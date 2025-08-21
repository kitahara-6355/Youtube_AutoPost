import argparse
import os
from google.cloud import firestore
from google.cloud import storage

# --- Firestore and GCS Clients ---
db = firestore.Client()
storage_client = storage.Client()
VIDEO_COLLECTION = "videos"
DOWNLOAD_DIR = "downloads"

def get_video_download_info(filename):
    """Firestoreから編集済み動画のGCSパスとステータスを取得する"""
    try:
        doc_ref = db.collection(VIDEO_COLLECTION).document(filename)
        doc = doc_ref.get()

        if not doc.exists:
            print(f"Error: File '{filename}' not found in the database.")
            return None

        video_data = doc.to_dict()
        status = video_data.get("edit_status")
        path = video_data.get("edited_video_path")

        print(f"Video '{filename}' found with status: {status}")

        # Transcoderジョブが完了したか、GCPコンソールで確認が必要な場合がある
        if status in ["PROCESSING", "COMPLETE"] and path:
            return path
        elif status == "PENDING":
             print("Error: Video has not been processed for editing yet.")
             return None
        else:
            print(f"Error: Video editing status is '{status}'. Not ready for download.")
            return None

    except Exception as e:
        print(f"Database query failed: {e}")
        return None

def download_from_gcs(gcs_path, destination_file_name):
    """GCSからファイルをダウンロードする"""
    try:
        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)

        blob = storage.Blob.from_string(gcs_path, client=storage_client)

        destination_path = os.path.join(DOWNLOAD_DIR, destination_file_name)
        blob.download_to_filename(destination_path)
        print(f"File {blob.name} downloaded to {destination_path}.")
        return True
    except Exception as e:
        print(f"Failed to download from GCS: {e}")
        return False

def update_download_status(filename, user_role):
    """Firestoreのダウンロードステータスを更新する"""
    if user_role not in ["main", "sub"]:
        print("Error: Invalid user role. Must be 'main' or 'sub'.")
        return

    try:
        doc_ref = db.collection(VIDEO_COLLECTION).document(filename)
        doc_ref.update({f"downloaded_by_{user_role}": True})
        print(f"Updated download status for '{filename}' for user '{user_role}'.")
    except Exception as e:
        print(f"Failed to update database: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download the edited video from GCS and update status.")
    parser.add_argument("original_filename", help="The name of the original file that was uploaded.")
    parser.add_argument("user_role", choices=["main", "sub"], help="The role of the user downloading the file (main/sub).")

    args = parser.parse_args()

    edited_gcs_path = get_video_download_info(args.original_filename)

    if edited_gcs_path:
        edited_filename = os.path.basename(edited_gcs_path)
        if download_from_gcs(edited_gcs_path, edited_filename):
            update_download_status(args.original_filename, args.user_role)
