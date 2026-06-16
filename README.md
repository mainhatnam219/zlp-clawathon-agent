# 🏆 Stock Knowledge Hub

### Trợ lý AI Tra Cứu Tri Thức Sản Phẩm Chứng Khoán Zalopay

> Biến hơn 140 tài liệu đặc tả sản phẩm, business rule và kiến thức nghiệp vụ thành một trợ lý AI có thể hỏi đáp bằng ngôn ngữ tự nhiên.

![Python](https://img.shields.io/badge/Python-3.13-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-ReAct-green)
![SQLite](https://img.shields.io/badge/SQLite-FTS5-orange)
![GreenNode](https://img.shields.io/badge/GreenNode-AgentBase-purple)

---

# 🎯 Bài toán thực tế

Trong quá trình phát triển sản phẩm chứng khoán trên Zalopay, đội ngũ Product, BA, QA và Engineering phải làm việc với lượng tài liệu rất lớn:

📚 Hơn 140 tài liệu đặc tả tính năng (PRD)

📖 Business Rules và quy trình nghiệp vụ

🏗 Architecture Decision Records (ADR)

💻 Source code và tài liệu kỹ thuật

Khi cần tìm một thông tin cụ thể, thành viên thường phải:

❌ Mở hàng chục file tài liệu

❌ Tìm kiếm trên nhiều repository

❌ Hỏi những người có kinh nghiệm lâu năm

❌ Tốn nhiều thời gian tra cứu hơn là thực hiện công việc

Tri thức đã tồn tại.

Nhưng việc tiếp cận tri thức vẫn còn khó khăn.

---

# 💡 Giải pháp

## Stock Knowledge Hub

Một AI Agent cho phép người dùng đặt câu hỏi bằng ngôn ngữ tự nhiên và nhận được câu trả lời chính xác từ toàn bộ kho tài liệu sản phẩm.

Ví dụ:

> "Acceptance criteria của lệnh MP là gì?"

> "Flow onboarding tài khoản chứng khoán hoạt động như thế nào?"

> "File nào xử lý nghiệp vụ nạp tiền?"

> "Giải thích Margin Call trong hệ thống hiện tại."

Thay vì trả về danh sách tài liệu, Agent sẽ:

✅ Tự động tìm kiếm

✅ Tổng hợp thông tin

✅ Liên kết nhiều nguồn tri thức

✅ Trả về câu trả lời hoàn chỉnh

---

# ✨ Tính năng nổi bật

## 🔎 Tra cứu tài liệu thông minh

Tìm kiếm trên toàn bộ:

* Product Requirement Documents (PRD)
* Business Rules
* User Flows
* ADR
* Product Glossary

---

## 🤖 AI Agent tự suy luận

Sử dụng LangGraph ReAct Agent.

Agent có khả năng:

* Hiểu ý định người dùng
* Chọn đúng công cụ tìm kiếm
* Kết hợp nhiều nguồn dữ liệu
* Tổng hợp thành câu trả lời dễ hiểu

Thay vì chỉ trả về kết quả search thô.

---

## 🔗 Kết nối Requirement → Implementation

Cho phép truy vết từ:

Business Requirement

⬇

Business Rule

⬇

Flow

⬇

Source Code

Người dùng có thể biết:

* Service nào xử lý
* Module nào liên quan
* File code nào implement

chỉ từ một câu hỏi.

---

## 🌏 Hỗ trợ song ngữ

Tự động nhận diện và trả lời bằng:

🇻🇳 Tiếng Việt

🇺🇸 English

---

## ⚡ Hiệu năng cao

* SQLite FTS5 Full Text Search
* BM25 Ranking
* Cache kết quả trong 7 ngày
* Streaming response qua SSE

Không cần:

❌ Elasticsearch

❌ Vector Database

❌ Hạ tầng phức tạp

---

# 🏗️ Kiến trúc hệ thống

```text
Người dùng
     │
     ▼

LangGraph ReAct Agent

     │
     ├── search_prd
     ├── search_requirements
     ├── search_kb
     ├── get_kb_detail
     ├── list_features
     └── find_code_refs

     │
     ▼

SQLite + FTS5

     ├── Product Documents
     ├── Business Rules
     ├── Flows
     ├── ADR
     └── Code References
```

---

# ⚙️ Công nghệ sử dụng

| Thành phần    | Công nghệ             |
| ------------- | --------------------- |
| AI Agent      | LangGraph + LangChain |
| LLM           | OpenAI Compatible API |
| Search Engine | SQLite FTS5           |
| Backend       | Python + Starlette    |
| Frontend      | Vanilla JS            |
| Streaming     | Server-Sent Events    |
| Database      | SQLite                |
| Container     | Docker                |
| Platform      | GreenNode AgentBase   |

---

# 🚀 Điểm đổi mới (Innovation)

## 1️⃣ Agentic Knowledge Retrieval

Không chỉ tìm kiếm tài liệu.

Agent có khả năng suy luận, lựa chọn công cụ phù hợp và tổng hợp câu trả lời từ nhiều nguồn dữ liệu.

---

## 2️⃣ Requirement-to-Code Mapping

Liên kết trực tiếp:

Yêu cầu nghiệp vụ → Thiết kế → Triển khai

Giúp giảm đáng kể thời gian onboarding, debugging và impact analysis.

---

## 3️⃣ Hạ tầng tối giản

Thay vì sử dụng:

* Elasticsearch
* OpenSearch
* Vector Database

Hệ thống chỉ cần:

✅ SQLite FTS5

✅ Một container Docker

vẫn đạt tốc độ truy vấn rất cao.

---

## 4️⃣ Sẵn sàng Production

Được thiết kế với:

* OAuth Authentication
* Streaming Response
* Response Cache
* Docker Deployment
* GreenNode AgentBase Integration

---

# 📈 Giá trị mang lại

## ⏳ Tiết kiệm thời gian tra cứu

Từ vài phút xuống còn vài giây.

---

## 🚀 Tăng tốc onboarding

Thành viên mới có thể hiểu sản phẩm nhanh hơn mà không phụ thuộc vào chuyên gia nghiệp vụ.

---

## 🧠 Lưu giữ tri thức tổ chức

Business rule và quyết định hệ thống không còn nằm trong trí nhớ của một vài cá nhân.

---

## 💰 Giảm chi phí vận hành

Không cần đầu tư thêm hạ tầng tìm kiếm chuyên biệt.

Triển khai đơn giản bằng một container duy nhất.

---

# 💬 Ví dụ câu hỏi

```text
Tính năng nạp tiền có những bước nào?

Acceptance criteria của MP Order là gì?

Flow onboarding hoạt động như thế nào?

File nào implement tính năng đặt lệnh?

Domain ví hiện có bao nhiêu tính năng?

What are the business rules for order matching?
```

---

# 🏅 Giá trị Hackathon

Stock Knowledge Hub hướng tới một mục tiêu đơn giản:

Biến toàn bộ tri thức sản phẩm thành một đồng đội AI.

Thay vì tìm kiếm tài liệu.

Người dùng chỉ cần đặt câu hỏi.

AI sẽ tìm kiếm, suy luận, kết nối và giải thích.

📚 Từ tài liệu → Tri thức

🧠 Từ tri thức → Hành động

⚡ Từ vài phút → vài giây

---

Built with ❤️ for Zalopay Clawathon

Powered by GreenNode AgentBase · LangGraph · SQLite FTS5
