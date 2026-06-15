"""PRD Knowledge Hub Agent — serves chat API + static web UI."""
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from greennode_agentbase import (
    GreenNodeAgentBaseApp,
    RequestContext,
    PingStatus,
)
import knowledge_db as db

load_dotenv()

# --- LLM ---
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
if not LLM_MODEL or not LLM_BASE_URL or not LLM_API_KEY:
    raise ValueError(
        "LLM_MODEL, LLM_BASE_URL, and LLM_API_KEY are required. "
        "Copy .env.example → .env and fill in the values."
    )

llm = ChatOpenAI(model=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

# --- Tools ---

@tool
def search_prd(query: str) -> str:
    """Search PRD documents by keyword or topic.
    Use this when the user asks about a feature, product area, or requirement.
    Returns matching PRD titles, domains, and summaries.
    """
    results = db.search_prd(query, limit=5)
    if not results:
        return "No PRD documents found matching that query."
    lines = []
    for r in results:
        lines.append(f"**[{r['id']}] {r['title']}** (domain: {r['domain']}, updated: {r['updated']})")
        if r.get("summary"):
            lines.append(f"  Summary: {r['summary'][:200]}")
        lines.append("")
    return "\n".join(lines)


@tool
def search_requirements(query: str) -> str:
    """Search specific requirement/acceptance criteria by keyword.
    Use this when the user asks about specific behavior, AC, or implementation detail.
    Returns requirement titles and bodies from matching PRDs.
    """
    results = db.search_requirements(query, limit=6)
    if not results:
        return "No requirements found matching that query."
    lines = []
    for r in results:
        lines.append(f"**[{r['prd_id']}] {r['prd_title']}** → Requirement {r['req_number']}: {r['title']}")
        if r.get("body"):
            lines.append(f"  {r['body'][:300]}")
        lines.append("")
    return "\n".join(lines)


@tool
def get_prd_detail(prd_id: str) -> str:
    """Get full detail of a PRD by its ID (confluence_page_id or filename stem).
    Use this when the user wants to read the full content of a specific PRD.
    """
    prd = db.get_prd(prd_id)
    if not prd:
        return f"PRD with ID '{prd_id}' not found. Try search_prd first to find the correct ID."
    lines = [
        f"# {prd['title']}",
        f"Domain: {prd['domain']} | Updated: {prd['updated']} | File: {prd['source_file']}",
        "",
        prd.get("summary", ""),
        "",
        "## Requirements",
    ]
    for req in prd.get("requirements", []):
        lines.append(f"### Requirement {req['req_number']}: {req['title']}")
        lines.append(req.get("body", "")[:600])
        lines.append("")
    return "\n".join(lines)


@tool
def list_features(domain: str = "") -> str:
    """List all features/PRDs, optionally filtered by domain.
    Domain options: stock, order, deposit, withdraw, onboarding, asset, payment,
    margin, notification, home, education, recommendation, watchlist, search,
    market, gifting, news, referral, loyalty, p2p, compliance, general.
    Leave domain empty to see all domains with counts.
    """
    if not domain:
        domains = db.list_domains()
        lines = ["## Available Domains\n"]
        for d in domains:
            lines.append(f"- **{d['domain']}**: {d['count']} PRD(s)")
        return "\n".join(lines)
    prds = db.list_prds(domain=domain, limit=30)
    if not prds:
        return f"No PRDs found for domain '{domain}'."
    lines = [f"## PRDs in domain: {domain}\n"]
    for p in prds:
        lines.append(f"- **[{p['id']}]** {p['title']} (updated: {p['updated']})")
        if p.get("summary"):
            lines.append(f"  {p['summary'][:120]}")
    return "\n".join(lines)


# --- Agent ---
SYSTEM_PROMPT = """You are a PRD Knowledge Hub assistant for a stock trading product (TKCK).
You have access to a database of Product Requirement Documents (PRDs) covering features like
stock trading, orders, deposits, withdrawals, margin trading, onboarding, home screen,
educational content, notifications, and more.

Help users:
- Find which PRD covers a specific feature or topic
- Look up acceptance criteria and requirements
- Understand what has been built or planned
- Navigate between related features

Always search the database before answering. Be concise and cite the PRD ID and title.
Respond in the same language as the user (Vietnamese or English)."""

agent = create_react_agent(
    llm,
    tools=[search_prd, search_requirements, get_prd_detail, list_features],
    prompt=SYSTEM_PROMPT,
)

# --- Web UI ---
STATIC_DIR = Path(__file__).parent / "static"

app = GreenNodeAgentBaseApp()


from starlette.responses import HTMLResponse
from starlette.routing import Route

async def serve_ui(request):
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)

app.routes.append(Route("/", serve_ui, methods=["GET"]))


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    message = payload.get("message", "").strip()
    if not message:
        return {"status": "error", "response": "Message is required."}

    result = agent.invoke(
        {"messages": [{"role": "user", "content": message}]}
    )
    ai_message = result["messages"][-1]
    return {
        "status": "success",
        "response": ai_message.content,
        "timestamp": datetime.now().isoformat(),
    }


@app.ping
def health_check() -> PingStatus:
    if not db.DB_PATH.exists():
        return PingStatus.UNHEALTHY
    return PingStatus.HEALTHY


if __name__ == "__main__":
    if not db.DB_PATH.exists():
        print("WARNING: knowledge.db not found. Run `python ingest.py` first.")
    app.run(port=8080, host="0.0.0.0")
