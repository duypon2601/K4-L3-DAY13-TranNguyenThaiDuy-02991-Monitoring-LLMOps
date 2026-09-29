# Evidence cá nhân

Đặt ảnh hoặc output text dùng để chấm vào thư mục này. Danh sách đầy đủ xem tại [docs/SUBMISSION.md](../../docs/SUBMISSION.md).

Tên file gợi ý:

```text
01-pytest.png
02-log-validator.png
03-dashboard-validator.png
04-structured-log.png
05-pii-redaction.png
06-trace-list.png
07-trace-waterfall.png
08-trace-metadata.png
09-prompt-versions.png
10-prompt-rollback.png
11-dashboard-overview.png
12-incident-metric.png
13-incident-log.png
14-incident-trace.png
```

Có thể dùng `.txt` cho output của tests/validators (01–03). Có thể tách dashboard thành nhiều ảnh nếu một ảnh không đọc rõ.

Ảnh `04`, `05`, `13` lấy từ terminal hoặc `data/logs.jsonl`. Ảnh `06`–`10`, `14` lấy từ project Langfuse cá nhân `day13-k4-l3a-<MSSV>` và nên nhìn thấy tên project. Không mở/chụp trang API Keys.

Từ `submission/REPORT.md`, dẫn ảnh bằng đường dẫn tương đối:

```markdown
![Trace waterfall](evidence/07-trace-waterfall.png)
```

## Lệnh tái tạo evidence dạng text

Các lệnh sau dùng để sinh hoặc tái tạo evidence dạng text và kiểm tra an toàn:

```bash
# 01 - Chạy bộ kiểm thử pytest
.venv/bin/python -m pytest -q > submission/evidence/01-pytest.txt

# 02 - Chạy log validator
.venv/bin/python scripts/validate_logs.py > submission/evidence/02-log-validator.txt

# 03 - Chạy dashboard validator
.venv/bin/python scripts/validate_dashboard.py > submission/evidence/03-dashboard-validator.txt

# Quét phát hiện secret và PII trong repository
.venv/bin/python scripts/scan_repo.py

# Dựng dashboard tĩnh 6 panel từ logs.jsonl
.venv/bin/python scripts/build_dashboard.py
```

Không commit secret, API key, PII thô hoặc evidence của học viên/lớp khác.
