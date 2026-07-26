import sqlite3
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS manga (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            cover_url TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY,
            manga_id TEXT NOT NULL,
            chapter_name TEXT NOT NULL,
            chapter_order INTEGER NOT NULL,
            url TEXT NOT NULL,
            downloaded INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (manga_id) REFERENCES manga(id)
        );

        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL,
            image_url TEXT NOT NULL,
            page_num INTEGER NOT NULL,
            local_path TEXT,
            downloaded INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id)
        );
    """)
    conn.commit()
    conn.close()


def save_manga(manga_id, name, url, cover_url=None, description=None):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO manga (id, name, url, cover_url, description) VALUES (?, ?, ?, ?, ?)",
        (manga_id, name, url, cover_url, description),
    )
    conn.commit()
    conn.close()


def get_manga(manga_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM manga WHERE id = ?", (manga_id,)).fetchone()
    conn.close()
    return row


def save_chapter(id, manga_id, chapter_name, chapter_order, url):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO chapters (id, manga_id, chapter_name, chapter_order, url) VALUES (?, ?, ?, ?, ?)",
        (id, manga_id, chapter_name, chapter_order, url),
    )
    conn.commit()
    conn.close()


def get_chapters(manga_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM chapters WHERE manga_id = ? ORDER BY chapter_order DESC", (manga_id,)
    ).fetchall()
    conn.close()
    return rows


def get_chapter_by_order(manga_id, chapter_order):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM chapters WHERE manga_id = ? AND chapter_order = ?",
        (manga_id, chapter_order),
    ).fetchone()
    conn.close()
    return row


def mark_chapter_downloaded(chapter_id):
    conn = get_conn()
    conn.execute("UPDATE chapters SET downloaded = 1 WHERE id = ?", (chapter_id,))
    conn.commit()
    conn.close()


def save_image(chapter_id, image_url, page_num, local_path=None):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO images (chapter_id, image_url, page_num, local_path, downloaded) VALUES (?, ?, ?, ?, ?)",
        (chapter_id, image_url, page_num, local_path, 1 if local_path else 0),
    )
    conn.commit()
    conn.close()


def get_images(chapter_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM images WHERE chapter_id = ? ORDER BY page_num", (chapter_id,)
    ).fetchall()
    conn.close()
    return rows
