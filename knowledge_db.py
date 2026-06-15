"""SQLite knowledge store for PRD documents."""
import sqlite3
import json
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "knowledge.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS prd_nodes (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                domain      TEXT,
                source_file TEXT,
                version     TEXT,
                updated     TEXT,
                summary     TEXT,
                full_text   TEXT
            );

            CREATE TABLE IF NOT EXISTS requirements (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                prd_id      TEXT NOT NULL,
                req_number  INTEGER,
                title       TEXT,
                body        TEXT,
                FOREIGN KEY (prd_id) REFERENCES prd_nodes(id)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS prd_fts USING fts5(
                id UNINDEXED,
                title,
                domain,
                summary,
                full_text,
                content=prd_nodes,
                content_rowid=rowid
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS req_fts USING fts5(
                prd_id UNINDEXED,
                req_number UNINDEXED,
                title,
                body,
                content=requirements,
                content_rowid=id
            );
        """)


def upsert_prd(prd: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO prd_nodes (id, title, domain, source_file, version, updated, summary, full_text)
            VALUES (:id, :title, :domain, :source_file, :version, :updated, :summary, :full_text)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, domain=excluded.domain,
                source_file=excluded.source_file, version=excluded.version,
                updated=excluded.updated, summary=excluded.summary,
                full_text=excluded.full_text
        """, prd)
        conn.execute("DELETE FROM requirements WHERE prd_id = ?", (prd["id"],))
        for req in prd.get("requirements", []):
            conn.execute("""
                INSERT INTO requirements (prd_id, req_number, title, body)
                VALUES (?, ?, ?, ?)
            """, (prd["id"], req["number"], req["title"], req["body"]))
        # Rebuild FTS
        conn.execute("INSERT INTO prd_fts(prd_fts) VALUES('rebuild')")
        conn.execute("INSERT INTO req_fts(req_fts) VALUES('rebuild')")


def search_prd(query: str, limit: int = 5) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT p.id, p.title, p.domain, p.source_file, p.updated, p.summary,
                   rank
            FROM prd_fts
            JOIN prd_nodes p ON prd_fts.id = p.id
            WHERE prd_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
        return [dict(r) for r in rows]


def search_requirements(query: str, limit: int = 8) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT r.prd_id, r.req_number, r.title, r.body,
                   p.title AS prd_title, p.domain, p.source_file,
                   rank
            FROM req_fts
            JOIN requirements r ON req_fts.rowid = r.id
            JOIN prd_nodes p ON r.prd_id = p.id
            WHERE req_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
        return [dict(r) for r in rows]


def get_prd(prd_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM prd_nodes WHERE id = ?", (prd_id,)).fetchone()
        if not row:
            return None
        prd = dict(row)
        reqs = conn.execute(
            "SELECT req_number, title, body FROM requirements WHERE prd_id = ? ORDER BY req_number",
            (prd_id,)
        ).fetchall()
        prd["requirements"] = [dict(r) for r in reqs]
        return prd


def list_domains() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT domain, COUNT(*) AS count
            FROM prd_nodes
            WHERE domain IS NOT NULL
            GROUP BY domain
            ORDER BY count DESC
        """).fetchall()
        return [dict(r) for r in rows]


def list_prds(domain: Optional[str] = None, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        if domain:
            rows = conn.execute(
                "SELECT id, title, domain, updated, summary FROM prd_nodes WHERE domain = ? ORDER BY updated DESC LIMIT ?",
                (domain, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, domain, updated, summary FROM prd_nodes ORDER BY updated DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
