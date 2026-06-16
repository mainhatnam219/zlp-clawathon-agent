"""Stock Knowledge Hub Agent — serves chat API + static web UI."""
import logging
import os
import time
import uuid
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
from knowledge_db import get_cached_response, set_cached_response

load_dotenv()

# ── Logging setup ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("prd_hub")


def _log(trace_id: str, event: str, **kwargs):
    """Structured single-line log with trace_id prefix."""
    parts = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    log.info("[%s] %s%s", trace_id, event, f" | {parts}" if parts else "")

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

# ── Tool trace_id context (thread-local per request) ──────────────────────
import threading
_ctx = threading.local()

def _tid() -> str:
    return getattr(_ctx, "trace_id", "no-trace")


# --- Tools ---

@tool
def search_prd(query: str, sub_area: str = "", doc_type: str = "") -> str:
    """Search PRD documents by keyword or topic.
    Use this when the user asks about a feature, product area, or requirement.

    Args:
        query: keywords or natural language query
        sub_area: optional filter — one of: onboarding, auth, deposit, withdraw, order, margin,
                  market-data, asset, education, gifting, home, growth, notification, system, convention, meta
        doc_type: optional filter — one of: prd, spec, reference, guide, convention, ab-test, summary

    Returns matching PRD titles, sub_area, use_when guidance, and summaries.
    """
    t0 = time.perf_counter()
    _log(_tid(), "tool:search_prd", query=repr(query[:60]), sub_area=sub_area or "-", doc_type=doc_type or "-")
    results = db.search_prd(query, limit=6, sub_area=sub_area, doc_type=doc_type)
    _log(_tid(), "tool:search_prd:done", hits=len(results), elapsed_ms=f"{(time.perf_counter()-t0)*1000:.0f}")
    if not results:
        return "No PRD documents found matching that query."
    lines = []
    for r in results:
        lines.append(f"**[{r['id']}] {r['title']}**")
        lines.append(f"  Area: {r.get('sub_area') or r.get('domain')} | Type: {r.get('type')} | Status: {r.get('status')} | Updated: {r.get('updated')}")
        if r.get("summary"):
            lines.append(f"  Summary: {r['summary'][:200]}")
        if r.get("use_when"):
            lines.append(f"  Use when: {r['use_when'][:150]}")
        lines.append("")
    return "\n".join(lines)


@tool
def search_requirements(query: str) -> str:
    """Search specific requirement/acceptance criteria by keyword.
    Use this when the user asks about specific behavior, AC, or implementation detail.
    Returns requirement titles and bodies from matching PRDs.
    """
    t0 = time.perf_counter()
    _log(_tid(), "tool:search_requirements", query=repr(query[:60]))
    results = db.search_requirements(query, limit=6)
    _log(_tid(), "tool:search_requirements:done", hits=len(results), elapsed_ms=f"{(time.perf_counter()-t0)*1000:.0f}")
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
    t0 = time.perf_counter()
    _log(_tid(), "tool:get_prd_detail", prd_id=prd_id)
    prd = db.get_prd(prd_id)
    _log(_tid(), "tool:get_prd_detail:done", found=prd is not None, elapsed_ms=f"{(time.perf_counter()-t0)*1000:.0f}")
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
    """List all features/PRDs, optionally filtered by domain/sub_area.
    Sub-area options: onboarding, auth, deposit, withdraw, order, margin,
    market-data, asset, education, gifting, home, growth, notification, system, convention, meta.
    Leave domain empty to see all sub-areas with counts.
    """
    _log(_tid(), "tool:list_features", domain=domain or "(all)")
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


@tool
def search_kb(query: str, sub_domain: str = "", kb_type: str = "") -> str:
    """Search the structured Knowledge Base (KB) for business rules, flow maps, glossary, risks, and ADRs.
    Use this when the user asks about HOW something works, business logic, cross-service flows, or design decisions.
    This complements search_prd (which covers WHAT was planned) with structured verified knowledge.

    Args:
        query: keywords or natural language
        sub_domain: optional filter — one of: order, funding, account, portfolio, market-data,
                    discovery, engagement, growth
        kb_type: optional filter — one of: business-rule, flow-map, glossary, risk, adr

    Returns KB entries with status (active/needs-review) and related services.
    """
    t0 = time.perf_counter()
    _log(_tid(), "tool:search_kb", query=repr(query[:60]), sub_domain=sub_domain or "-", kb_type=kb_type or "-")
    results = db.search_kb(query, limit=5, sub_domain=sub_domain, kb_type=kb_type)
    _log(_tid(), "tool:search_kb:done", hits=len(results), elapsed_ms=f"{(time.perf_counter()-t0)*1000:.0f}")
    if not results:
        return "No KB entries found matching that query."
    lines = []
    for r in results:
        lines.append(f"**[{r['id']}]** (sub_domain: {r['sub_domain']}, type: {r['type']}, status: {r['status']})")
        services = r.get("related_services", "")
        if services and services != "[]":
            lines.append(f"  Services: {services}")
        if r.get("excerpt"):
            lines.append(f"  {r['excerpt'][:250]}")
        lines.append("")
    return "\n".join(lines)


@tool
def get_kb_detail(kb_id: str) -> str:
    """Get full detail of a KB node by its ID, including code file references.
    Use this when the user wants to read the full business rule, flow, or glossary entry,
    or when they ask 'where is this implemented in code?'
    """
    t0 = time.perf_counter()
    _log(_tid(), "tool:get_kb_detail", kb_id=kb_id)
    kb = db.get_kb_detail(kb_id)
    _log(_tid(), "tool:get_kb_detail:done", found=kb is not None, elapsed_ms=f"{(time.perf_counter()-t0)*1000:.0f}")
    if not kb:
        return f"KB entry '{kb_id}' not found. Try search_kb first."
    lines = [
        f"# KB: {kb_id}",
        f"Sub-domain: {kb['sub_domain']} | Type: {kb['type']} | Status: {kb['status']}",
        f"Services: {kb.get('related_services', '[]')}",
        f"Last verified: {kb.get('last_verified', 'unknown')}",
        "",
        kb.get("full_text", ""),
    ]
    code_refs = kb.get("code_refs", [])
    if code_refs:
        lines.append("\n## Code References")
        for ref in code_refs:
            line_info = f":{ref['line_number']}" if ref.get("line_number") else ""
            lines.append(f"- `{ref['file_path']}{line_info}` (service: {ref['service']})")
    return "\n".join(lines)


@tool
def find_code_refs(query: str) -> str:
    """Find source code file references related to a feature or flow.
    Use this when the user asks 'where is X implemented?', 'which file handles Y?',
    or 'what code is related to this flow?'
    Returns file paths and line numbers from the KB code_refs index.
    """
    t0 = time.perf_counter()
    _log(_tid(), "tool:find_code_refs", query=repr(query[:60]))
    results = db.find_code_refs(query, limit=8)
    _log(_tid(), "tool:find_code_refs:done", hits=len(results), elapsed_ms=f"{(time.perf_counter()-t0)*1000:.0f}")
    if not results:
        return "No code references found for that query. Try search_kb to find the relevant KB entry first."
    lines = ["## Code References Found\n"]
    seen = set()
    for r in results:
        ref = r["ref"]
        if ref in seen:
            continue
        seen.add(ref)
        line_info = f":{r['line_number']}" if r.get("line_number") else ""
        lines.append(f"- **`{r['file_path']}{line_info}`** (service: `{r['service']}`)")
        lines.append(f"  From KB: [{r['kb_id']}] ({r['sub_domain']}/{r['type']})")
        if r.get("context"):
            lines.append(f"  Context: {r['context'][:120]}")
        lines.append("")
    return "\n".join(lines)


# --- Agent ---
SYSTEM_PROMPT = """You are a Stock Knowledge Hub assistant for a stock trading product (TKCK — Tài Khoản Chứng Khoán on ZaloPay).
You have access to 140+ indexed feature documents with rich metadata including sub_area, use_when, topics, and status.

Sub-areas available: onboarding, auth, deposit, withdraw, order, margin, market-data, asset,
education, gifting, home, growth, notification, system, convention, meta.

Document types: prd (full feature spec), spec (detailed logic/validation), reference (tables/APIs),
guide (user guide), convention (naming/color rules), ab-test (experiments).

IMPORTANT — Language rules for responses:
- NEVER use the word "PRD" when responding to users. Instead say:
  "tài liệu đặc tả tính năng", "đặc tả", "tài liệu", "tài liệu chức năng", or simply the feature name.
- Example: instead of "PRD về deposit", say "tài liệu chức năng Deposit" or "đặc tả tính năng nạp tiền".
- You may still use internal IDs like prd-stock-deposit as reference codes, but call them "mã tài liệu" or "ID tài liệu".

Two knowledge sources available:
1. **Feature docs** (search_prd, get_prd_detail, search_requirements, list_features):
   WHAT was planned — features, acceptance criteria, UI flows, product decisions.
2. **Knowledge Base / KB** (search_kb, get_kb_detail, find_code_refs):
   HOW it works — business rules, cross-service flow maps, glossary, risks, code references.
   KB also contains code_refs pointing to actual source files (file:line).

Retrieval strategy:
- "what is feature X?" or "how does feature Y work?" → search_prd first
- "business rule for Y", "which services are involved?", "flow map" → search_kb
- "where is X implemented?", "which file handles Y?" → find_code_refs
- For deep dives, combine both sources on the same topic
- Prefer status=current (feature docs) and status=active (KB); flag needs-review explicitly

Always cite document IDs as reference. Respond in the same language as the user (Vietnamese or English)."""

agent = create_react_agent(
    llm,
    tools=[search_prd, search_requirements, get_prd_detail, list_features,
           search_kb, get_kb_detail, find_code_refs],
    prompt=SYSTEM_PROMPT,
)

# LLM for streaming (same config, explicit streaming=True)
llm_stream = ChatOpenAI(
    model=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY, streaming=True
)
agent_stream = create_react_agent(
    llm_stream,
    tools=[search_prd, search_requirements, get_prd_detail, list_features,
           search_kb, get_kb_detail, find_code_refs],
    prompt=SYSTEM_PROMPT,
)

# --- Web UI ---
STATIC_DIR = Path(__file__).parent / "static"

app = GreenNodeAgentBaseApp()


from starlette.requests import Request
from starlette.responses import HTMLResponse, StreamingResponse
from starlette.routing import Route


async def serve_ui(request: Request):
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


async def stream_chat(request: Request):
    """SSE endpoint: streams agent tokens as they arrive."""
    trace_id = uuid.uuid4().hex[:10]
    body = await request.json()
    message = body.get("message", "").strip()

    if not message:
        async def err():
            yield "data: [ERROR] Message is required\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    _log(trace_id, "stream:start", msg_len=len(message), preview=repr(message[:60]))

    # ── Cache check ──
    cached = get_cached_response(message)
    if cached:
        _log(trace_id, "stream:cache_hit", chars=len(cached))
        async def from_cache():
            import asyncio
            chunk_size = 6  # small chunks → smooth appearance
            for i in range(0, len(cached), chunk_size):
                chunk = cached[i:i + chunk_size]
                yield f"data: {chunk.replace(chr(10), chr(92) + 'n')}\n\n"
                await asyncio.sleep(0.012)  # ~80 chars/s ≈ real LLM feel
            yield "data: [DONE]\n\n"
        return StreamingResponse(
            from_cache(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Cache": "HIT"},
        )

    async def event_stream():
        _ctx.trace_id = trace_id
        t0 = time.perf_counter()
        tool_calls = 0
        tokens = 0
        accumulated = ""
        try:
            async for event in agent_stream.astream_events(
                {"messages": [{"role": "user", "content": message}]},
                version="v2",
            ):
                kind = event.get("event", "")

                if kind == "on_tool_start":
                    tool_calls += 1
                    tool_name = event.get("name", "?")
                    tool_input = event.get("data", {}).get("input", {})
                    _log(trace_id, f"agent:tool_start", tool=tool_name,
                         input=repr(str(tool_input)[:80]))

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "?")
                    out = event.get("data", {}).get("output", "")
                    _log(trace_id, f"agent:tool_end", tool=tool_name,
                         output_len=len(str(out)))

                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        content = chunk.content
                        if isinstance(content, str):
                            tokens += len(content)
                            accumulated += content
                            if tokens % 200 < len(content):
                                _log(trace_id, "stream:tokens", tokens=tokens)
                            yield f"data: {content.replace(chr(10), '\\n')}\n\n"
                        elif isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    tokens += len(part["text"])
                                    accumulated += part["text"]
                                    if tokens % 200 < len(part["text"]):
                                        _log(trace_id, "stream:tokens", tokens=tokens)
                                    yield f"data: {part['text'].replace(chr(10), '\\n')}\n\n"

            elapsed = time.perf_counter() - t0
            _log(trace_id, "stream:done",
                 elapsed_ms=f"{elapsed*1000:.0f}",
                 tool_calls=tool_calls,
                 tokens_streamed=tokens)
            if accumulated:
                set_cached_response(message, accumulated)
                _log(trace_id, "stream:cached", chars=len(accumulated))
            yield "data: [DONE]\n\n"

        except Exception as e:
            _log(trace_id, "stream:error", error=str(e))
            yield f"data: [ERROR] {e}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


app.routes.append(Route("/", serve_ui, methods=["GET"]))
app.routes.append(Route("/stream", stream_chat, methods=["POST"]))


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    trace_id = uuid.uuid4().hex[:10]
    _ctx.trace_id = trace_id
    message = payload.get("message", "").strip()

    _log(trace_id, "invoke:start", msg_len=len(message), preview=repr(message[:60]))
    if not message:
        return {"status": "error", "response": "Message is required."}

    t0 = time.perf_counter()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": message}]}
    )
    ai_message = result["messages"][-1]
    elapsed = time.perf_counter() - t0

    # Count tool calls from message history
    tool_calls = sum(1 for m in result["messages"] if hasattr(m, "type") and m.type == "tool")
    _log(trace_id, "invoke:done",
         elapsed_ms=f"{elapsed*1000:.0f}",
         tool_calls=tool_calls,
         response_len=len(ai_message.content))

    return {
        "status": "success",
        "response": ai_message.content,
        "timestamp": datetime.now().isoformat(),
        "trace_id": trace_id,
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
