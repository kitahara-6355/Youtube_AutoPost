import sqlite3

DB_NAME = "video_status.db"

def setup_database():
    """
    データベースとテーブルを初期化する。
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # videosテーブルが存在しない場合のみ作成
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL UNIQUE,
        gcs_path TEXT NOT NULL,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        downloaded_by_main BOOLEAN DEFAULT 0,
        downloaded_by_sub BOOLEAN DEFAULT 0,
        deleted_from_gcs BOOLEAN DEFAULT 0
    )
    """)

    # BOOLEANはSQLiteではINTEGER 0 (false) or 1 (true) として扱われる

    conn.commit()
    conn.close()
    print(f"Database '{DB_NAME}' and table 'videos' are set up successfully.")

if __name__ == "__main__":
    setup_database()
