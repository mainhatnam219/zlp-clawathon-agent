# Stock Knowledge Hub — AI Agent cho Sản phẩm Chứng Khoán Zalopay

> **Agent tra cứu tài liệu sản phẩm bằng ngôn ngữ tự nhiên** — tích hợp 140+ tài liệu đặc tả tính năng và knowledge base nghiệp vụ của nền tảng TKCK trên Zalopay.

---

## Agent giải quyết vấn đề gì?

Khi phát triển sản phẩm chứng khoán (TKCK — Tài Khoản Chứng Khoán trên Zalopay), đội ngũ sản phẩm và kỹ thuật phải làm việc với khối lượng tài liệu rất lớn:

- **Nhiều tài liệu đặc tả tính năng (PRD)** trải rộng trên nhiều domain: nạp tiền, lệnh giao dịch, onboarding, ví, sao kê...
- **Knowledge Base nghiệp vụ** mô tả luồng xử lý, business rule, các thay đổi của hệ thống
- **Thông tin phân tán** không có điểm tra cứu tập trung — tìm một tính năng phải mở hàng chục file, tìm một business rule phải hỏi người, tra một đoạn code phải đoán tên file

**Stock Knowledge Hub giải quyết bằng cách:**
- Cung cấp một giao diện hỏi-đáp
- Agent tự động tra cứu đúng tài liệu, tổng hợp câu trả lời thay vì trả về link thô
- Kết nối được từ câu hỏi nghiệp vụ → đặc tả tính năng → file source code cụ thể

---

## Ai là người sử dụng?

| Vai trò | Nhu cầu điển hình |
|---|---|
| **Product Manager / BA** | "Tính năng rút tiền có những acceptance criteria nào?" / "Domain ví có bao nhiêu tính năng?" |
| **Software Engineer** | "Flow đặt lệnh hoạt động như thế nào?" / "File nào xử lý logic deposit?" |
| **QA / Tester** | "Điều kiện để lệnh MP được khớp là gì?" / "Onboarding flow có những edge case nào?" |
| **Thành viên mới** | "Giải thích kiến trúc tổng thể TKCK cho tôi" / "Từ điển thuật ngữ chứng khoán trong sản phẩm" |

---

## Agent hoạt động như thế nào?

### Kiến trúc tổng quan

```
Người dùng (Web UI / GreenNode Platform)
        │
        ▼
  [Flask / Starlette Web Server]
        │
        ▼
  [LangGraph ReAct Agent]  ←── System Prompt (TKCK context, language rules)
        │
        ├── search_prd          → Tìm kiếm tài liệu đặc tả theo từ khóa
        ├── search_requirements → Tìm acceptance criteria cụ thể
        ├── get_prd_detail      → Lấy toàn bộ nội dung một tài liệu
        ├── list_features       → Liệt kê tính năng theo domain
        ├── search_kb           → Tìm trong knowledge base nghiệp vụ
        ├── get_kb_detail       → Xem chi tiết một entry KB
        └── find_code_refs      → Tìm file source code liên quan
                │
                ▼
        [SQLite + FTS5 Full-Text Search]
         ├── prd_nodes (140+ feature docs)
         └── kb_nodes (business rules, flows, ADRs, glossary)
```

### Luồng xử lý một câu hỏi

1. **Người dùng gửi câu hỏi** qua giao diện web hoặc GreenNode Platform API
2. **Kiểm tra cache** — nếu câu hỏi tương tự đã được trả lời trong 7 ngày qua, trả về kết quả ngay (stream giả lập để UX nhất quán)
3. **ReAct Agent suy luận** — LLM phân tích câu hỏi, chọn tool phù hợp, thực thi, quan sát kết quả, lặp lại nếu cần
4. **Full-text search** qua SQLite FTS5 — tìm kiếm xếp hạng theo độ liên quan (BM25)
5. **Tổng hợp câu trả lời** — LLM kết hợp kết quả từ nhiều tool, viết câu trả lời dạng markdown
6. **Stream real-time** qua SSE (Server-Sent Events) — người dùng thấy câu trả lời xuất hiện từng token

### Pipeline nạp dữ liệu (Ingestion)

```
PRD Markdown files + INDEX.yaml
        │
        ▼
  ingest.py → parse frontmatter, trích xuất nội dung
        │
        ▼
  knowledge.db (SQLite)
  ├── prd_nodes + prd_fts (FTS5 index)
  └── kb_nodes + kb_fts + code_refs
```

### Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Agent Framework | LangGraph (ReAct pattern) + LangChain |
| LLM | OpenAI-compatible API (hỗ trợ GreenNode AIP, OpenAI, v.v.) |
| Database | SQLite với FTS5 full-text search |
| Backend | Python, Starlette/Flask, Server-Sent Events |
| Frontend | Vanilla JS, dark theme UI, marked.js, localStorage |
| Platform | GreenNode AgentBase (VNG Cloud) |
| Container | Docker (Python 3.13-slim, port 8080) |

---

## Giá trị mà Agent mang lại

### 1. Tiết kiệm thời gian tra cứu
Thay vì mở 10–20 file để tìm một thông tin, người dùng hỏi một câu và nhận câu trả lời tổng hợp trong vài giây.

### 2. Kết nối đặc tả → implementation
Agent có thể trả lời "tính năng X được implement ở file nào, dòng nào" — kết nối trực tiếp từ yêu cầu nghiệp vụ đến source code, giảm thời gian onboarding và debug.

### 3. Tri thức tổ chức không phụ thuộc vào cá nhân
Toàn bộ business rule, flow, ADR được index và truy vấn được — giảm phụ thuộc vào "người biết" trong team, đặc biệt khi có thành viên mới hoặc khi rotate.

### 4. Tích hợp sẵn vào GreenNode AgentBase
Chạy trên nền tảng AI agent của VNG Cloud với xác thực OAuth, monitoring, và hỗ trợ cả Web UI lẫn API invocation — sẵn sàng cho production.

---

## Cài đặt & Chạy thử

### Yêu cầu

```bash
# Clone repo
git clone https://github.com/mainhatnam219/zlp-clawathon-agent.git
cd zlp-clawathon-agent

# Tạo file .env từ template
cp .env.example .env
# Điền GREENNODE_CLIENT_ID, GREENNODE_CLIENT_SECRET, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
```

### Nạp dữ liệu

```bash
# Đặt PRD markdown files vào mock-prd/ và INDEX.yaml
# Đặt KB files vào project-kb/
python ingest.py
```

### Chạy local

```bash
pip install -r requirements.txt
python main.py
# Mở http://localhost:8080
```

### Chạy với Docker

```bash
docker build -t stock-knowledge-hub .
docker run -p 8080:8080 --env-file .env stock-knowledge-hub
```

---

## Ví dụ câu hỏi

```
"Tính năng nạp tiền có những bước nào?"
"Acceptance criteria của lệnh thị trường (MP order) là gì?"
"File nào trong codebase xử lý luồng onboarding?"
"Giải thích khái niệm margin call trong sản phẩm TKCK"
"Domain ví có bao nhiêu tính năng đã đặc tả?"
"What are the business rules for order matching?"
```

---

*Built for Zalopay Clawathon · Powered by GreenNode AgentBase · LangGraph ReAct Agent*
