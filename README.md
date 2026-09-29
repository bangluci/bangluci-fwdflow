# FwdFlow

Hệ thống quản lý lô hàng nhập khẩu door-to-door cho forwarder vừa và nhỏ, tích hợp AI đọc + đối chiếu chứng từ, gợi ý mã HS và hỏi đáp dữ liệu bằng tiếng Việt. Đồ án tốt nghiệp.

- Spec: [docs/specs/2026-09-24-forwarder-door-to-door-ai-design.md](docs/specs/2026-09-24-forwarder-door-to-door-ai-design.md)
- Plan: [docs/plans/2026-09-24-forwarder-door-to-door-ai.md](docs/plans/2026-09-24-forwarder-door-to-door-ai.md)

## Chạy dev (Windows PowerShell)

```powershell
Copy-Item .env.example .env
docker compose up -d db mailpit caddy
python -m uv sync --directory api
python -m uv run --directory api alembic upgrade head
python -m uv run --directory api uvicorn app.main:app --port 8000
npm --prefix web install
npm --prefix web run dev
```

Mở http://localhost:8088 (Caddy gom web + `/api`). Mailpit: http://127.0.0.1:8025.

## Tài khoản demo

Đặt `SEED_PASSWORD` (≥ 10 ký tự) trong `.env`, rồi:

```powershell
python -m uv run --directory api python -m scripts.seed_demo --reset --seed 1 --size small
```

`--size small` (20 lô / 50 container / 200 đơn giao) hoặc `full` (200 / 500 / 2000, khoảng 20 giây); `--as-of YYYY-MM-DD` cố định ngày tham chiếu (mặc định hôm nay). Không có `--size` thì chỉ tạo danh mục và tài khoản.

Dữ liệu là mô phỏng. Mọi tài khoản dùng chung mật khẩu `SEED_PASSWORD`:

- `admin@fwdflow.local`, `docs@fwdflow.local`, `dispatch@fwdflow.local`, `accountant@fwdflow.local`
- `customer@fwdflow.local` (khách hàng số 1)
- `0900000006` (tài xế, đăng nhập bằng SĐT)

## AI #2 (gợi ý mã HS): dữ liệu và model

Chạy được không cần các bước này (gợi ý rút gọn, chỉ full-text). Muốn đủ tính năng, cài một lần (cần khoảng 3 GB trống):

```powershell
python -m uv sync --directory api --group hs                      # sentence-transformers + torch (CPU)
# Model bge-m3 (~2,3 GB) vào models/bge-m3 (git ignore); chỉ tải các tệp cần dùng
python -m uv run --directory api python -c "from huggingface_hub import snapshot_download as d; d('BAAI/bge-m3', local_dir='../models/bge-m3', allow_patterns=['config.json','config_sentence_transformers.json','modules.json','sentence_bert_config.json','1_Pooling/*','pytorch_model.bin','sentencepiece.bpe.model','special_tokens_map.json','tokenizer.json','tokenizer_config.json'])"
# Danh mục TT 31/2022: 18 PDF của Công báo vào data/hs/tt31-2022/ (xem docs/review/2026-09-29-kiem-chung-hs.md)
python -m uv run --directory api python -m app.ai.hs.importer ../data/hs/tt31-2022
python -m uv run --directory api python -m app.ai.hs.embed          # ~1-2 giờ trên CPU, chạy lại sẽ làm tiếp
```

Đặt `EMBED_PRELOAD=true` trong `.env` để API nạp model ngay khi khởi động.

## Test

```powershell
python -m uv run --directory api pytest -q
npm --prefix web run lint
npm --prefix web run test:e2e   # Playwright; stack chạy ở :8088, API với AI_EXTERNAL_ENABLED=false
```
