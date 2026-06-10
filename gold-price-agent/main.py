import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
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


def _fetch_source(source: str, api_key: str) -> dict[str, Any]:
    url = f"{VNAPPMOB_BASE}/{source}?api_key={api_key}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "gold-price-agent/1.0",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_payload(payload: dict[str, Any]) -> tuple[str, list[str]]:
    source = str(payload.get("source", "all")).strip().lower()
    message = str(payload.get("message", "")).strip().lower()

    if source == "all" and message:
        for item in SUPPORTED_SOURCES:
            if item in message:
                return item, [item]
        if "tất cả" in message or "all" in message:
            return "all", list(SUPPORTED_SOURCES)

    if source in SUPPORTED_SOURCES:
        return source, [source]
    if source == "all":
        return "all", list(SUPPORTED_SOURCES)

    return "all", list(SUPPORTED_SOURCES)


def _format_vnd(value: Any) -> str | None:
    if value is None:
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{amount:,.0f} VND/lượng"


def _summarize_source(source: str, raw: dict[str, Any]) -> dict[str, Any]:
    results = raw.get("results")
    if not isinstance(results, list) or not results:
        return {
            "source": source,
            "label": SOURCE_LABELS.get(source, source.upper()),
            "raw": raw,
            "summary": "Không có dữ liệu giá vàng.",
        }

    latest = results[0]
    summary_lines = [f"Giá vàng {SOURCE_LABELS.get(source, source.upper())} mới nhất:"]

    if source == "sjc":
        pairs = [
            ("Mua 1 lượng", latest.get("buy_1l")),
            ("Bán 1 lượng", latest.get("sell_1l")),
            ("Mua 1 chỉ", latest.get("buy_1c")),
            ("Bán 1 chỉ", latest.get("sell_1c")),
            ("Mua nhẫn 1 chỉ", latest.get("buy_nhan1c")),
            ("Bán nhẫn 1 chỉ", latest.get("sell_nhan1c")),
        ]
    elif source == "doji":
        pairs = [
            ("Mua HCM", latest.get("buy_hcm")),
            ("Bán HCM", latest.get("sell_hcm")),
            ("Mua HN", latest.get("buy_hn")),
            ("Bán HN", latest.get("sell_hn")),
        ]
    else:
        pairs = [
            ("Mua HCM", latest.get("buy_hcm")),
            ("Bán HCM", latest.get("sell_hcm")),
            ("Mua HN", latest.get("buy_hn")),
            ("Bán HN", latest.get("sell_hn")),
        ]

    for label, value in pairs:
        formatted = _format_vnd(value)
        if formatted:
            summary_lines.append(f"- {label}: {formatted}")

    return {
        "source": source,
        "label": SOURCE_LABELS.get(source, source.upper()),
        "prices": latest,
        "summary": "\n".join(summary_lines),
        "raw": raw,
    }


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    """Fetch latest Vietnamese gold prices from VNAppMob.

    Payload examples:
      {"source": "sjc"}
      {"source": "all"}
      {"message": "giá vàng SJC hôm nay"}
    """
    api_key = os.environ.get("GOLD_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "error",
            "message": (
                "GOLD_API_KEY chưa được cấu hình. "
                "Đăng ký miễn phí tại: "
                "https://api.vnappmob.com/api/request_api_key?scope=gold"
            ),
            "session_id": context.session_id,
        }

    _, sources = _normalize_payload(payload or {})
    fetched_at = datetime.now(timezone.utc).isoformat()
    quotes: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for source in sources:
        try:
            raw = _fetch_source(source, api_key)
            quotes.append(_summarize_source(source, raw))
        except HTTPError as exc:
            errors.append(
                {
                    "source": source,
                    "error": f"HTTP {exc.code}: {exc.reason}",
                }
            )
        except URLError as exc:
            errors.append({"source": source, "error": str(exc.reason)})
        except json.JSONDecodeError:
            errors.append(
                {"source": source, "error": "Phản hồi API không phải JSON hợp lệ."}
            )

    if not quotes:
        return {
            "status": "error",
            "message": "Không lấy được giá vàng từ bất kỳ nguồn nào.",
            "errors": errors,
            "fetched_at": fetched_at,
            "session_id": context.session_id,
        }

    summary = "\n\n".join(item["summary"] for item in quotes)
    return {
        "status": "success",
        "message": summary,
        "quotes": quotes,
        "errors": errors or None,
        "fetched_at": fetched_at,
        "session_id": context.session_id,
    }


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
