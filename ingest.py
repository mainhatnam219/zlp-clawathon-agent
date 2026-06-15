"""Ingest PRD markdown files into the knowledge SQLite database.

Usage:
    python ingest.py [--prd-dir mock-prd]
"""
import re
import sys
import argparse
from pathlib import Path
from typing import Optional

from knowledge_db import init_db, upsert_prd


def extract_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML-like frontmatter and return (meta, body)."""
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


def extract_domain(title: str, source_file: str) -> str:
    """Infer domain from title or filename."""
    title_lower = title.lower()
    file_lower = source_file.lower()
    mapping = {
        "stock": ["stock", "screener", "simplize", "filter", "ticker"],
        "order": ["order", "buy", "sell", "mua", "bán"],
        "deposit": ["deposit", "nạp tiền", "nap"],
        "withdraw": ["withdraw", "rút tiền", "rut"],
        "onboarding": ["onboarding", "registration", "đăng ký"],
        "asset": ["asset", "portfolio", "tài sản"],
        "payment": ["payment", "vnpay", "thanh toán"],
        "margin": ["margin"],
        "notification": ["notification", "noti", "zns"],
        "home": ["home", "homepage"],
        "education": ["education", "educational", "học"],
        "recommendation": ["recommendation", "gợi ý"],
        "watchlist": ["watch", "watchlist"],
        "search": ["search", "tìm kiếm"],
        "market": ["market", "thị trường"],
        "gifting": ["gift", "gifting"],
        "news": ["news", "tin tức"],
        "referral": ["referral"],
        "loyalty": ["loyalty", "crm"],
        "p2p": ["p2p"],
        "margin": ["margin"],
        "compliance": ["fatca", "aml", "compliance", "legal"],
        "convention": ["convention", "rule", "color"],
    }
    combined = title_lower + " " + file_lower
    for domain, keywords in mapping.items():
        if any(kw in combined for kw in keywords):
            return domain
    return "general"


def extract_requirements(body: str) -> list[dict]:
    """Extract numbered requirement sections from the body."""
    requirements = []
    # Match patterns like "Requirement 1", "Requirement 2", etc.
    pattern = re.compile(r"(?:^|\n)(?:##?\s+)?Requirement\s+(\d+)(.*?)(?=(?:\n##?\s+Requirement\s+\d+)|$)", re.DOTALL | re.IGNORECASE)
    matches = list(pattern.finditer(body))

    if matches:
        for m in matches:
            num = int(m.group(1))
            content = m.group(2).strip()
            # First line as title, rest as body
            lines = content.splitlines()
            title = lines[0].strip(" \t#-") if lines else f"Requirement {num}"
            req_body = "\n".join(lines[1:]).strip() if len(lines) > 1 else content
            # Truncate body for storage
            requirements.append({
                "number": num,
                "title": title or f"Requirement {num}",
                "body": req_body[:2000],
            })
    else:
        # Fallback: use Acceptance Criteria section
        ac_match = re.search(r"##+\s*Acceptance criteria(.*?)(?=\n##|\Z)", body, re.DOTALL | re.IGNORECASE)
        if ac_match:
            requirements.append({
                "number": 1,
                "title": "Acceptance Criteria",
                "body": ac_match.group(1).strip()[:2000],
            })

    return requirements


def make_summary(meta: dict, body: str) -> str:
    """Create a short summary from the PRD."""
    # Try Overall section
    overall = re.search(r"##+\s*Overall\s*\n(.*?)(?=\n##|\Z)", body, re.DOTALL | re.IGNORECASE)
    if overall:
        return overall.group(1).strip()[:500]
    # Try Context section
    context = re.search(r"##+\s*Context\s*\n(.*?)(?=\n##|\Z)", body, re.DOTALL | re.IGNORECASE)
    if context:
        return context.group(1).strip()[:500]
    # Fallback: first non-empty paragraph
    for para in body.split("\n\n"):
        para = para.strip()
        if para and not para.startswith("#") and len(para) > 30:
            return para[:500]
    return ""


def ingest_file(path: Path) -> Optional[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    meta, body = extract_frontmatter(text)

    title = meta.get("title", path.stem)
    prd_id = meta.get("confluence_page_id", path.stem)
    domain = extract_domain(title, path.name)
    requirements = extract_requirements(body)
    summary = make_summary(meta, body)

    # Clean HTML entities for full_text search
    clean_body = re.sub(r"&[a-z]+;", " ", body)
    clean_body = re.sub(r"!\[.*?\]\(.*?\)", "", clean_body)  # remove image refs
    clean_body = re.sub(r"\s+", " ", clean_body).strip()

    return {
        "id": str(prd_id),
        "title": title,
        "domain": domain,
        "source_file": path.name,
        "version": meta.get("version", ""),
        "updated": meta.get("updated", ""),
        "summary": summary,
        "full_text": clean_body[:10000],
        "requirements": requirements,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prd-dir", default="mock-prd", help="Directory with PRD markdown files")
    args = parser.parse_args()

    prd_dir = Path(args.prd_dir)
    if not prd_dir.exists():
        print(f"ERROR: Directory '{prd_dir}' not found.", file=sys.stderr)
        sys.exit(1)

    print("Initializing database...")
    init_db()

    md_files = sorted(prd_dir.glob("*.md"))
    print(f"Found {len(md_files)} markdown files in '{prd_dir}'")

    ok, skipped = 0, 0
    for path in md_files:
        try:
            prd = ingest_file(path)
            if prd:
                upsert_prd(prd)
                print(f"  [OK] {path.name} → domain={prd['domain']}, reqs={len(prd['requirements'])}")
                ok += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  [ERR] {path.name}: {e}")
            skipped += 1

    print(f"\nDone. Ingested: {ok}, Skipped/Error: {skipped}")
    print(f"Knowledge DB saved to: knowledge.db")


if __name__ == "__main__":
    main()
