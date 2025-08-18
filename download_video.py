import argparse
import os
import sqlite3
from google.cloud import storage

DB_NAME = "video_status.db"
DOWNLOAD_DIR = "downloads"

def get_gcs_path(filename):
    """データベースからGCSのパスを取得する"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT gcs_path FROM videos WHERE filename = ?", (filename,))
        result = cursor.fetchone()
        conn.close()
        if result:
            return result[0]
        else:
            print(f"Error: File '{filename}' not found in the database.")
            return None
    except Exception as e:
        print(f"Database query failed: {e}")
        return None

def download_from_gcs(gcs_path, destination_file_name):
    """GCSからファイルをダウンロードする"""
    try:
        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)

        storage_client = storage.Client()
        blob = storage.Blob.from_string(gcs_path, client=storage_client)

        destination_path = os.path.join(DOWNLOAD_DIR, destination_file_name)
        blob.download_to_filename(destination_path)
        print(f"File {blob.name} downloaded to {destination_path}.")
        return True
    except Exception as e:
        print(f"Failed to download from GCS: {e}")
        return False

def update_download_status(filename, user_role):
    """ダウンロードステータスをデータベースで更新する"""
    if user_role not in ["main", "sub"]:
        print("Error: Invalid user role. Must be 'main' or 'sub'.")
        return

    column_to_update = f"downloaded_by_{user_role}"

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE videos SET {column_to_update} = 1 WHERE filename = ?", (filename,))
        conn.commit()
        conn.close()
        print(f"Updated download status for '{filename}' for user '{user_role}'.")
    except Exception as e:
        print(f"Failed to update database: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download a file from GCS and update status.")
    parser.add_argument("filename", help="The name of the file to download.")
    parser.add_argument("user_role", choices=["main", "sub"], help="The role of the user downloading the file (main/sub).")

    args = parser.parse_args()

    gcs_path = get_gcs_path(args.filename)

    if gcs_path:
        if download_from_gcs(gcs_path, args.filename):
            update_download_status(args.filename, args.user_role)
