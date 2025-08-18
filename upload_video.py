import argparse
import os
import sqlite3
from google.cloud import storage

DB_NAME = "video_status.db"

def upload_to_gcs(bucket_name, source_file_name, destination_blob_name):
    """GCSにファイルをアップロードする"""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file_name)
        print(f"File {source_file_name} uploaded to gs://{bucket_name}/{destination_blob_name}.")
        return f"gs://{bucket_name}/{destination_blob_name}"
    except Exception as e:
        print(f"Failed to upload to GCS: {e}")
        return None

def record_upload_in_db(filename, gcs_path):
    """アップロード情報をデータベースに記録する"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO videos (filename, gcs_path) VALUES (?, ?)", (filename, gcs_path)
        )
        conn.commit()
        conn.close()
        print(f"Recorded upload of {filename} to database.")
    except sqlite3.IntegrityError:
        print(f"File '{filename}' already exists in the database. Skipping record.")
    except Exception as e:
        print(f"Failed to record to database: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Upload a file to GCS and record it in the database."
    )
    parser.add_argument("bucket_name", help="The name of the GCS bucket.")
    parser.add_argument("source_file_name", help="The local path of the file to upload.")

    args = parser.parse_args()

    destination_blob_name = os.path.basename(args.source_file_name)

    # まずGCSにアップロード
    gcs_path = upload_to_gcs(args.bucket_name, args.source_file_name, destination_blob_name)

    # アップロードが成功した場合のみデータベースに記録
    if gcs_path:
        record_upload_in_db(destination_blob_name, gcs_path)
