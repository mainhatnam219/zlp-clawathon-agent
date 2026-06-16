"""Ingest PRD documents into the knowledge SQLite database.

Two modes:
  1. Index mode (recommended): reads INDEX.yaml for rich metadata, loads markdown for full_text
     python ingest.py --index INDEX.yaml --prd-dir mock-prd
  2. Legacy mode: scans a folder of markdown files (no index, keyword-based domain)
     python ingest.py --prd-dir mock-prd
"""
import re
import sys
import json

import argparse
from pathlib import Path
from typing import Optional

import yaml

from knowledge_db import init_db, upsert_prd, upsert_kb


# ---------------------------------------------------------------------------
# Index-based ingestion (primary path)
# ---------------------------------------------------------------------------

def load_index(index_path: Path) -> list[dict]:
    """Load INDEX.yaml and return list of document entries."""
    with open(index_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("documents", [])


def load_markdown_body(prd_dir: Path, filename: str) -> str:
    """Load full text from the markdown file, stripping frontmatter."""
    path = prd_dir / filename
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    # Strip YAML frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].strip()
    # Clean up for FTS
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:12000]


def ingest_from_index(index_path: Path, prd_dir: Path) -> tuple[int, int]:
    entries = load_index(index_path)
    ok, skipped = 0, 0

    for entry in entries:
        # Skip container pages (body-less parent pages)
        if entry.get("type") == "container":
            print(f"  [SKIP] {entry.get('id')} — container page")
            skipped += 1
            continue

        topics = entry.get("topics", [])
        topics_str = " ".join(str(t) for t in topics) if isinstance(topics, list) else str(topics)

        full_text = load_markdown_body(prd_dir, entry.get("path", ""))
        if not full_text:
            # Still ingest metadata even if file missing
            full_text = f"{entry.get('summary', '')} {topics_str} {entry.get('use_when', '')}"

        prd = {
            "id": entry["id"],
            "title": entry.get("title", entry["id"]),
            "domain": entry.get("domain", "stock"),
            "sub_area": entry.get("sub_area", ""),
            "type": entry.get("type", "prd"),
            "source_file": entry.get("path", ""),
            "version": "",
            "updated": entry.get("date", ""),
            "status": entry.get("status", "current"),
            "summary": entry.get("summary", ""),
            "use_when": entry.get("use_when", ""),
            "topics": topics_str,
            "full_text": full_text,
            "requirements": [],
        }

        try:
            upsert_prd(prd)
            print(f"  [OK] {entry['id']} | {entry.get('sub_area')} | {entry.get('type')} | status={entry.get('status')}")
            ok += 1
        except Exception as e:
            print(f"  [ERR] {entry.get('id')}: {e}")
            skipped += 1

    return ok, skipped


# ---------------------------------------------------------------------------
# Project-KB ingestion
# ---------------------------------------------------------------------------

def parse_kb_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from KB files; handles list values."""
    meta: dict = {}
    if not text.startswith("---"):
        return meta, text
    end = text.find("---", 3)
    if end == -1:
        return meta, text
    fm_block = text[3:end]
    body = text[end + 3:].strip()

    # Line-by-line parse: handles scalars, inline lists, and multiline lists
    current_key = None
    for line in fm_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Indented list item → belongs to current_key
        if (line.startswith("  ") or line.startswith("\t")) and stripped.startswith("- "):
            if current_key is not None:
                meta.setdefault(current_key, [])
                if isinstance(meta[current_key], list):
                    meta[current_key].append(stripped.lstrip("- ").strip())
            continue
        # Top-level key: value
        if ":" in stripped and not stripped.startswith("-"):
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip().strip('"')
            current_key = k
            if v.startswith("[") and v.endswith("]"):
                items = [i.strip().strip('"') for i in v[1:-1].split(",") if i.strip()]
                meta[k] = items
            elif v == "":
                meta[k] = []  # Will be filled by subsequent list items
            else:
                meta[k] = v
    return meta, body


def parse_code_refs(refs_raw) -> list[dict]:
    """Convert code_refs frontmatter value into structured list."""
    if not refs_raw:
        return []
    if isinstance(refs_raw, str):
        refs_raw = [refs_raw]
    result = []
    for ref in refs_raw:
        ref = ref.strip()
        if not ref:
            continue
        # Extract service from path prefix (first path segment)
        parts = ref.split("/")
        service = parts[0] if parts else ""
        # Split file path and optional line number
        if ":" in ref:
            file_path, _, line = ref.rpartition(":")
        else:
            file_path, line = ref, ""
        result.append({"ref": ref, "service": service, "file_path": file_path, "line_number": line})
    return result


def ingest_kb_file(path: Path, kb_root: Path) -> Optional[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    meta, body = parse_kb_frontmatter(text)

    kb_id = meta.get("id", "")
    if not kb_id:
        return None  # Skip files without id

    # Derive sub_domain from directory structure: project-kb/domains/stock/<sub_domain>/
    try:
        rel = path.relative_to(kb_root)
        parts = rel.parts  # e.g. ('domains', 'stock', 'order', 'flows', 'place-order.md')
        sub_domain = parts[2] if len(parts) > 2 else ""
    except ValueError:
        sub_domain = ""

    related = meta.get("related_services", [])
    if isinstance(related, str):
        related = [s.strip() for s in related.split(",") if s.strip()]

    clean_body = re.sub(r"\s+", " ", body).strip()

    return {
        "id": kb_id,
        "domain": meta.get("domain", "stock"),
        "sub_domain": sub_domain or meta.get("sub_domain", ""),
        "type": meta.get("type", ""),
        "related_services": json.dumps(related),
        "status": meta.get("status", "active"),
        "source_file": str(path.relative_to(Path.cwd()) if path.is_absolute() else path),
        "last_verified": meta.get("last_verified", ""),
        "full_text": clean_body[:12000],
        "code_refs": parse_code_refs(meta.get("code_refs", [])),
    }


def ingest_kb(kb_dir: Path) -> tuple[int, int]:
    md_files = sorted(kb_dir.rglob("*.md"))
    print(f"Found {len(md_files)} KB markdown files in '{kb_dir}'")
    ok, skipped = 0, 0
    for path in md_files:
        try:
            kb = ingest_kb_file(path, kb_dir)
            if kb:
                upsert_kb(kb)
                refs_count = len(kb.get("code_refs", []))
                print(f"  [KB] {kb['id']} | {kb['sub_domain']} | {kb['type']} | refs={refs_count} | status={kb['status']}")
                ok += 1
            else:
                print(f"  [SKIP] {path.name} — no id in frontmatter")
                skipped += 1
        except Exception as e:
            print(f"  [ERR] {path.name}: {e}")
            skipped += 1
    return ok, skipped


# ---------------------------------------------------------------------------
# Legacy ingestion (fallback — no index file)
# ---------------------------------------------------------------------------

def extract_frontmatter(text: str) -> tuple[dict, str]:
    meta = {}
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm = text[3:end].strip()
            for line in fm.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip().strip('"')
            text = text[end + 3:].strip()
    return meta, text


def extract_requirements(body: str) -> list[dict]:
    requirements = []
    pattern = re.compile(
        r"(?:^|\n)(?:##?\s+)?Requirement\s+(\d+)(.*?)(?=(?:\n##?\s+Requirement\s+\d+)|$)",
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(body):
        num = int(m.group(1))
        content = m.group(2).strip()
        lines = content.splitlines()
        title = lines[0].strip(" \t#-") if lines else f"Requirement {num}"
        req_body = "\n".join(lines[1:]).strip() if len(lines) > 1 else content
        requirements.append({"number": num, "title": title or f"Requirement {num}", "body": req_body[:2000]})

    if not requirements:
        ac_match = re.search(r"##+\s*Acceptance criteria(.*?)(?=\n##|\Z)", body, re.DOTALL | re.IGNORECASE)
        if ac_match:
            requirements.append({"number": 1, "title": "Acceptance Criteria", "body": ac_match.group(1).strip()[:2000]})

    return requirements


def make_summary(body: str) -> str:
    for section in ["Overall", "Context"]:
        m = re.search(rf"##+\s*{section}\s*\n(.*?)(?=\n##|\Z)", body, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()[:500]
    for para in body.split("\n\n"):
        para = para.strip()
        if para and not para.startswith("#") and len(para) > 30:
            return para[:500]
    return ""


def ingest_legacy_file(path: Path) -> Optional[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    meta, body = extract_frontmatter(text)

    title = meta.get("title", path.stem)
    prd_id = meta.get("confluence_page_id", path.stem)
    requirements = extract_requirements(body)
    summary = make_summary(body)

    clean_body = re.sub(r"&[a-z]+;", " ", body)
    clean_body = re.sub(r"!\[.*?\]\(.*?\)", "", clean_body)
    clean_body = re.sub(r"\s+", " ", clean_body).strip()

    return {
        "id": str(prd_id),
        "title": title,
        "domain": "stock",
        "sub_area": "",
        "type": "prd",
        "source_file": path.name,
        "version": meta.get("version", ""),
        "updated": meta.get("updated", ""),
        "status": "current",
        "summary": summary,
        "use_when": "",
        "topics": "",
        "full_text": clean_body[:10000],
        "requirements": requirements,
    }


def ingest_legacy(prd_dir: Path) -> tuple[int, int]:
    md_files = sorted(prd_dir.glob("*.md"))
    print(f"Found {len(md_files)} markdown files in '{prd_dir}' (legacy mode)")
    ok, skipped = 0, 0
    for path in md_files:
        try:
            prd = ingest_legacy_file(path)
            if prd:
                upsert_prd(prd)
                print(f"  [OK] {path.name} → reqs={len(prd['requirements'])}")
                ok += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  [ERR] {path.name}: {e}")
            skipped += 1
    return ok, skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ingest PRD knowledge into SQLite.")
    parser.add_argument("--index", default="INDEX.yaml", help="Path to INDEX.yaml (index mode)")
    parser.add_argument("--prd-dir", default="mock-prd", help="Directory with PRD markdown files")
    parser.add_argument("--kb-dir", default="project-kb", help="Directory with project-kb markdown files")
    parser.add_argument("--legacy", action="store_true", help="Force legacy mode (no index)")
    args = parser.parse_args()

    print("Initializing database...")
    init_db()

    index_path = Path(args.index)
    prd_dir = Path(args.prd_dir)
    kb_dir = Path(args.kb_dir)

    # --- PRD ingestion ---
    if not args.legacy and index_path.exists():
        print(f"\n[PRD] Index mode: reading from {index_path} + {prd_dir}/")
        prd_ok, prd_skip = ingest_from_index(index_path, prd_dir)
    elif prd_dir.exists():
        print(f"\n[PRD] Legacy mode: scanning {prd_dir}/")
        prd_ok, prd_skip = ingest_legacy(prd_dir)
    else:
        print(f"WARNING: Neither index '{index_path}' nor PRD dir '{prd_dir}' found — skipping PRD.", file=sys.stderr)
        prd_ok, prd_skip = 0, 0

    # --- KB ingestion ---
    kb_ok, kb_skip = 0, 0
    if kb_dir.exists():
        print(f"\n[KB] Ingesting project-kb from {kb_dir}/")
        kb_ok, kb_skip = ingest_kb(kb_dir)
    else:
        print(f"WARNING: KB dir '{kb_dir}' not found — skipping KB.", file=sys.stderr)

    print(f"\n=== Done ===")
    print(f"PRD: ingested={prd_ok}, skipped={prd_skip}")
    print(f"KB:  ingested={kb_ok},  skipped={kb_skip}")
    print(f"Knowledge DB: knowledge.db")


if __name__ == "__main__":
    main()
