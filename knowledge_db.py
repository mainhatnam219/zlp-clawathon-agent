"""SQLite knowledge store for PRD documents."""
import hashlib
import sqlite3
import json
import re
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
            CREATE TABLE IF NOT EXISTS kb_nodes (
                id               TEXT PRIMARY KEY,
                domain           TEXT,
                sub_domain       TEXT,
                type             TEXT,
                related_services TEXT,
                status           TEXT DEFAULT 'active',
                source_file      TEXT,
                last_verified    TEXT,
                full_text        TEXT
            );

            CREATE TABLE IF NOT EXISTS code_refs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                kb_id       TEXT NOT NULL,
                ref         TEXT NOT NULL,
                service     TEXT,
                file_path   TEXT,
                line_number TEXT,
                FOREIGN KEY (kb_id) REFERENCES kb_nodes(id)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
                id UNINDEXED,
                domain,
                sub_domain,
                type,
                related_services,
                full_text,
                content=kb_nodes,
                content_rowid=rowid
            );

            CREATE TABLE IF NOT EXISTS prd_nodes (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                domain      TEXT,
                sub_area    TEXT,
                type        TEXT,
                source_file TEXT,
                version     TEXT,
                updated     TEXT,
                status      TEXT DEFAULT 'current',
                summary     TEXT,
                use_when    TEXT,
                topics      TEXT,
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
                sub_area,
                summary,
                use_when,
                topics,
                full_text,
                content=prd_nodes,
                content_rowid=rowid
            );

            CREATE TABLE IF NOT EXISTS response_cache (
                query_hash  TEXT PRIMARY KEY,
                query       TEXT NOT NULL,
                response    TEXT NOT NULL,
                hits        INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now')),
                expires_at  TEXT DEFAULT (datetime('now', '+7 days'))
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
            INSERT INTO prd_nodes
                (id, title, domain, sub_area, type, source_file, version, updated,
                 status, summary, use_when, topics, full_text)
            VALUES
                (:id, :title, :domain, :sub_area, :type, :source_file, :version, :updated,
                 :status, :summary, :use_when, :topics, :full_text)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                domain=excluded.domain,
                sub_area=excluded.sub_area,
                type=excluded.type,
                source_file=excluded.source_file,
                version=excluded.version,
                updated=excluded.updated,
                status=excluded.status,
                summary=excluded.summary,
                use_when=excluded.use_when,
                topics=excluded.topics,
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


def search_prd(query: str, limit: int = 5, sub_area: str = "", doc_type: str = "") -> list[dict]:
    with get_conn() as conn:
        filters = ["prd_fts MATCH ?", "p.status != 'superseded'"]
        params: list = [query]
        if sub_area:
            filters.append("p.sub_area = ?")
            params.append(sub_area)
        if doc_type:
            filters.append("p.type = ?")
            params.append(doc_type)
        where = " AND ".join(filters)
        params.append(limit)
        rows = conn.execute(f"""
            SELECT p.id, p.title, p.domain, p.sub_area, p.type, p.source_file,
                   p.updated, p.status, p.summary, p.use_when, rank
            FROM prd_fts
            JOIN prd_nodes p ON prd_fts.id = p.id
            WHERE {where}
            ORDER BY rank
            LIMIT ?
        """, params).fetchall()
        return [dict(r) for r in rows]


def search_requirements(query: str, limit: int = 8) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT r.prd_id, r.req_number, r.title, r.body,
                   p.title AS prd_title, p.domain, p.sub_area, p.source_file,
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
            SELECT sub_area AS domain, COUNT(*) AS count
            FROM prd_nodes
            WHERE sub_area IS NOT NULL AND status != 'superseded'
            GROUP BY sub_area
            ORDER BY count DESC
        """).fetchall()
        return [dict(r) for r in rows]


def upsert_kb(kb: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO kb_nodes
                (id, domain, sub_domain, type, related_services, status, source_file, last_verified, full_text)
            VALUES
                (:id, :domain, :sub_domain, :type, :related_services, :status, :source_file, :last_verified, :full_text)
            ON CONFLICT(id) DO UPDATE SET
                domain=excluded.domain, sub_domain=excluded.sub_domain,
                type=excluded.type, related_services=excluded.related_services,
                status=excluded.status, source_file=excluded.source_file,
                last_verified=excluded.last_verified, full_text=excluded.full_text
        """, kb)
        conn.execute("DELETE FROM code_refs WHERE kb_id = ?", (kb["id"],))
        for ref in kb.get("code_refs", []):
            conn.execute("""
                INSERT INTO code_refs (kb_id, ref, service, file_path, line_number)
                VALUES (?, ?, ?, ?, ?)
            """, (kb["id"], ref["ref"], ref.get("service", ""), ref.get("file_path", ""), ref.get("line_number", "")))
        conn.execute("INSERT INTO kb_fts(kb_fts) VALUES('rebuild')")


def search_kb(query: str, limit: int = 5, sub_domain: str = "", kb_type: str = "") -> list[dict]:
    with get_conn() as conn:
        filters = ["kb_fts MATCH ?", "k.status != 'deprecated'"]
        params: list = [query]
        if sub_domain:
            filters.append("k.sub_domain = ?")
            params.append(sub_domain)
        if kb_type:
            filters.append("k.type = ?")
            params.append(kb_type)
        where = " AND ".join(filters)
        params.append(limit)
        rows = conn.execute(f"""
            SELECT k.id, k.domain, k.sub_domain, k.type, k.related_services,
                   k.status, k.source_file, k.last_verified,
                   substr(k.full_text, 1, 400) AS excerpt,
                   rank
            FROM kb_fts
            JOIN kb_nodes k ON kb_fts.id = k.id
            WHERE {where}
            ORDER BY rank
            LIMIT ?
        """, params).fetchall()
        return [dict(r) for r in rows]


def get_kb_detail(kb_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM kb_nodes WHERE id = ?", (kb_id,)).fetchone()
        if not row:
            return None
        kb = dict(row)
        refs = conn.execute(
            "SELECT ref, service, file_path, line_number FROM code_refs WHERE kb_id = ? ORDER BY id",
            (kb_id,)
        ).fetchall()
        kb["code_refs"] = [dict(r) for r in refs]
        return kb


def find_code_refs(query: str, limit: int = 8) -> list[dict]:
    """Find code file references by searching KB nodes, return code_refs with context."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT cr.ref, cr.service, cr.file_path, cr.line_number,
                   k.id AS kb_id, k.sub_domain, k.type,
                   substr(k.full_text, 1, 200) AS context
            FROM code_refs cr
            JOIN kb_nodes k ON cr.kb_id = k.id
            JOIN kb_fts ON kb_fts.id = k.id
            WHERE kb_fts MATCH ?
            ORDER BY kb_fts.rank
            LIMIT ?
        """, (query, limit)).fetchall()
        return [dict(r) for r in rows]


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.lower().strip())


def _cache_key(query: str) -> str:
    return hashlib.sha256(_normalize_query(query).encode()).hexdigest()


def get_cached_response(query: str) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT response FROM response_cache WHERE query_hash = ? AND expires_at > datetime('now')",
            (_cache_key(query),)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE response_cache SET hits = hits + 1 WHERE query_hash = ?",
                (_cache_key(query),)
            )
            return row[0]
    return None


def set_cached_response(query: str, response: str):
    key = _cache_key(query)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO response_cache (query_hash, query, response)
            VALUES (?, ?, ?)
            ON CONFLICT(query_hash) DO UPDATE SET
                response=excluded.response,
                created_at=datetime('now'),
                expires_at=datetime('now', '+7 days'),
                hits=0
        """, (key, _normalize_query(query), response))


def list_prds(domain: Optional[str] = None, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        if domain:
            rows = conn.execute(
                """SELECT id, title, domain, sub_area, type, updated, status, summary
                   FROM prd_nodes
                   WHERE (sub_area = ? OR domain = ?) AND status != 'superseded'
                   ORDER BY updated DESC LIMIT ?""",
                (domain, domain, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, title, domain, sub_area, type, updated, status, summary
                   FROM prd_nodes WHERE status != 'superseded'
                   ORDER BY updated DESC LIMIT ?""",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
