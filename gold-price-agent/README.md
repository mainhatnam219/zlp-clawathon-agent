# gold-price-agent

Agent GreenNode AgentBase lấy giá vàng Việt Nam mới nhất từ SJC, DOJI và PNJ (qua VNAppMob API).

## Prerequisites

- Python 3.10+
- GreenNode IAM Service Account ([tạo tại đây](https://iam.console.vngcloud.vn/service-accounts))
- VNAppMob API key miễn phí ([đăng ký tại đây](https://api.vnappmob.com/api/request_api_key?scope=gold))

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Thêm GOLD_API_KEY vào .env
```

## Run Locally

```bash
python3 main.py
```

Test:

```bash
curl http://127.0.0.1:8080/health

curl -X POST http://127.0.0.1:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"source": "sjc"}'

curl -X POST http://127.0.0.1:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"source": "all"}'
```

## Deploy

Dùng skill `/agentbase-deploy` hoặc AgentBase Console.
