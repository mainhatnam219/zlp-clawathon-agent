import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from greennode_agentbase import GreenNodeAgentBaseApp, PingStatus, RequestContext

load_dotenv()

app = GreenNodeAgentBaseApp()

VNAPPMOB_BASE = "https://api.vnappmob.com/api/v2/gold"
SUPPORTED_SOURCES = ("sjc", "doji", "pnj")
SOURCE_LABELS = {
    "sjc": "SJC",
    "doji": "DOJI",
    "pnj": "PNJ",
}

SYSTEM_PROMPT = """Bạn là chuyên gia phân tích giá vàng Việt Nam.
Nhiệm vụ:
- Luôn gọi tool để lấy dữ liệu giá mới nhất trước khi phân tích.
- Trả lời bằng tiếng Việt, rõ ràng, có cấu trúc (tóm tắt, so sánh, nhận xét, lưu ý).
- Nêu rõ giá mua/bán, chênh lệch mua-bán (spread), so sánh giữa SJC/DOJI/PNJ nếu có.
- Không bịa số liệu; chỉ dùng dữ liệu từ tool.
- Thêm disclaimer ngắn: thông tin tham khảo, không phải lời khuyên đầu tư.
"""


def _get_api_key() -> str:
    return os.environ.get("GOLD_API_KEY", "").strip()


def _fetch_source(source: str, api_key: str) -> dict[str, Any]:
    url = f"{VNAPPMOB_BASE}/{source}?api_key={api_key}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "gold-price-agent/2.0",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _format_vnd(value: Any) -> str | None:
    if value is None:
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{amount:,.0f} VND"


def _summarize_source(source: str, raw: dict[str, Any]) -> dict[str, Any]:
    results = raw.get("results")
    if not isinstance(results, list) or not results:
        return {
            "source": source,
            "label": SOURCE_LABELS.get(source, source.upper()),
            "error": "Không có dữ liệu",
        }

    latest = results[0]
    if source == "sjc":
        fields = {
            "buy_1l": latest.get("buy_1l"),
            "sell_1l": latest.get("sell_1l"),
            "buy_1c": latest.get("buy_1c"),
            "sell_1c": latest.get("sell_1c"),
            "buy_nhan1c": latest.get("buy_nhan1c"),
            "sell_nhan1c": latest.get("sell_nhan1c"),
        }
    else:
        fields = {
            "buy_hcm": latest.get("buy_hcm"),
            "sell_hcm": latest.get("sell_hcm"),
            "buy_hn": latest.get("buy_hn"),
            "sell_hn": latest.get("sell_hn"),
        }

    formatted = {key: _format_vnd(value) for key, value in fields.items() if value is not None}
    return {
        "source": source,
        "label": SOURCE_LABELS.get(source, source.upper()),
        "prices": latest,
        "formatted": formatted,
    }


def _collect_quotes(sources: list[str]) -> dict[str, Any]:
    api_key = _get_api_key()
    if not api_key:
        return {
            "error": (
                "GOLD_API_KEY chưa được cấu hình. "
                "Đăng ký tại https://api.vnappmob.com/api/request_api_key?scope=gold"
            )
        }

    quotes: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for source in sources:
        try:
            raw = _fetch_source(source, api_key)
            quotes.append(_summarize_source(source, raw))
        except HTTPError as exc:
            errors.append({"source": source, "error": f"HTTP {exc.code}: {exc.reason}"})
        except URLError as exc:
            errors.append({"source": source, "error": str(exc.reason)})
        except json.JSONDecodeError:
            errors.append({"source": source, "error": "JSON không hợp lệ"})

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "quotes": quotes,
        "errors": errors or None,
    }


@tool
def get_gold_price(source: str = "sjc") -> str:
    """Lấy giá vàng mới nhất từ một nguồn: sjc, doji, hoặc pnj."""
    normalized = source.strip().lower()
    if normalized not in SUPPORTED_SOURCES:
        return json.dumps(
            {"error": f"Nguồn không hợp lệ: {source}. Chọn: sjc, doji, pnj."},
            ensure_ascii=False,
        )
    return json.dumps(_collect_quotes([normalized]), ensure_ascii=False)


@tool
def get_all_gold_prices() -> str:
    """Lấy giá vàng mới nhất từ tất cả nguồn SJC, DOJI, PNJ để so sánh."""
    return json.dumps(_collect_quotes(list(SUPPORTED_SOURCES)), ensure_ascii=False)


def _build_agent():
    llm_model = os.environ.get("LLM_MODEL", "").strip()
    llm_base_url = os.environ.get("LLM_BASE_URL", "").strip()
    llm_api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not llm_model or not llm_base_url or not llm_api_key:
        raise ValueError(
            "Thiếu LLM_MODEL, LLM_BASE_URL hoặc LLM_API_KEY. "
            "Dùng /agentbase-llm để cấu hình GreenNode AI Platform."
        )

    llm = ChatOpenAI(
        model=llm_model,
        base_url=llm_base_url,
        api_key=llm_api_key,
        temperature=0.2,
    )
    return create_agent(
        llm,
        tools=[get_gold_price, get_all_gold_prices],
        system_prompt=SYSTEM_PROMPT,
    )


_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = _build_agent()
    return _agent


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    """Phân tích giá vàng bằng AI.

    Payload:
      {"message": "Phân tích giá vàng SJC hôm nay"}
      {"message": "So sánh giá SJC, DOJI, PNJ"}
    """
    message = str((payload or {}).get("message", "")).strip()
    if not message:
        message = "Phân tích giá vàng mới nhất tại Việt Nam."

    if not _get_api_key():
        return {
            "status": "error",
            "message": (
                "GOLD_API_KEY chưa được cấu hình. "
                "Đăng ký miễn phí tại: "
                "https://api.vnappmob.com/api/request_api_key?scope=gold"
            ),
            "session_id": context.session_id,
        }

    try:
        result = _get_agent().invoke(
            {"messages": [{"role": "user", "content": message}]}
        )
        ai_message = result["messages"][-1]
        return {
            "status": "success",
            "message": message,
            "analysis": ai_message.content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": context.session_id,
        }
    except ValueError as exc:
        return {
            "status": "error",
            "message": str(exc),
            "session_id": context.session_id,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Lỗi khi phân tích: {exc}",
            "session_id": context.session_id,
        }


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


STATIC_DIR = Path(__file__).parent / "static"


async def ui_page(_request):
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


async def api_quotes(request):
    source = request.query_params.get("source", "all").strip().lower()
    if source == "all":
        sources = list(SUPPORTED_SOURCES)
    elif source in SUPPORTED_SOURCES:
        sources = [source]
    else:
        return JSONResponse(
            {"error": f"Nguồn không hợp lệ: {source}"},
            status_code=400,
        )
    return JSONResponse(_collect_quotes(sources))


app.routes.append(Route("/", ui_page, methods=["GET"]))
app.routes.append(Route("/api/quotes", api_quotes, methods=["GET"]))


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
