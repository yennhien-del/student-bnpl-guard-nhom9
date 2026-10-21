# 🛡️ Student BNPL Guard

WebApp giúp sinh viên quản lý chi tiêu cá nhân, theo dõi các khoản **mua trước trả sau (BNPL)** và hỏi **Guard AI** để được tư vấn dựa trên số liệu thật.

- **Công nghệ:** Python · Streamlit · SQLite · Pandas · Plotly · python-dotenv · API mô hình ngôn ngữ lớn (Anthropic hoặc OpenAI-compatible)
- **Giao diện:** tiếng Việt, VNĐ, ngày DD/MM/YYYY, responsive (desktop và điện thoại)
- **Dữ liệu:** lưu trong SQLite (`data/guard.db`), còn nguyên sau khi khởi động lại

## Cài đặt và chạy

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # (tùy chọn) điền API key để dùng Guard AI
streamlit run app.py
```

Mở http://localhost:8501. Lần đầu, màn hình Tổng quan cho chọn **Nạp dữ liệu demo** hoặc **Bắt đầu với dữ liệu trống**. Cũng có thể nạp demo bằng dòng lệnh: `python -m guard.seed` (thêm `--force` để xóa dữ liệu cũ và nạp lại).

> Nếu bắt đầu với dữ liệu trống, hãy vào **Cài đặt → Số dư ban đầu** trước. Chưa có số dư ban đầu và thu nhập thì mục «Kiểm tra trước khi mua» sẽ báo **Chưa đủ dữ liệu**.

## Cấu hình Guard AI

API key **không** nằm trong mã nguồn. Đặt trong `.env` hoặc Streamlit Secrets:

| Biến | Ý nghĩa |
|---|---|
| `LLM_PROVIDER` | `anthropic` (mặc định) hoặc `openai` (mọi API tương thích OpenAI) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | khóa API |
| `LLM_MODEL` | tên mô hình (mặc định `claude-sonnet-5-5` hoặc `gpt-4o-mini`) |
| `OPENAI_BASE_URL` | tùy chọn, cho endpoint tương thích OpenAI |

Streamlit Cloud: dán các biến trên vào **App settings → Secrets** (hoặc `.streamlit/secrets.toml` khi chạy cục bộ).

Chưa cấu hình key thì mọi chức năng quản lý tài chính vẫn chạy; chatbot chỉ hiển thị thông báo «chưa được cấu hình».

**Về quyền riêng tư:** khi bạn đặt câu hỏi, một bản tóm tắt số liệu (thu chi, ngân sách, lịch BNPL, giao dịch gần đây) được gửi tới nhà cung cấp AI bạn chọn. Có thể xem chính xác nội dung này ở mục «Dữ liệu Guard AI được phép dùng» trong trang Guard AI.

## Tính năng

| Trang | Nội dung |
|---|---|
| 📊 Tổng quan | KPI: thu nhập tháng, chi tiêu thực tế, số dư hiện tại, nghĩa vụ BNPL còn lại, BNPL đến hạn, số dư dự kiến; cảnh báo; biểu đồ cơ cấu chi tiêu và ngân sách so với thực tế; giao dịch gần đây |
| 💰 Ngân sách | Thêm/sửa/xóa nguồn thu (một lần hoặc hằng tháng), chi phí cố định, ngân sách theo danh mục và tháng, thanh tỷ lệ sử dụng, sao chép ngân sách từ tháng trước |
| 🧾 Chi tiêu | Thêm/sửa/xóa giao dịch, tìm kiếm, lọc danh mục và khoảng ngày, thống kê theo ngày/tuần/tháng |
| 💳 BNPL | Nhập thủ công khoản mua, tự tạo lịch trả góp, ghi nhận thanh toán đủ hoặc một phần, hoàn tác thanh toán, trạng thái quá hạn/sắp đến hạn |
| 🛒 Kiểm tra trước khi mua | Trả ngay hoặc BNPL: số dư trước/sau theo từng tháng, tổng nghĩa vụ từng tháng, mức rủi ro kèm lý do |
| 🤖 Guard AI | Chatbot phân tích chi tiêu, giải thích vượt ngân sách, gợi ý tiết kiệm, đánh giá khoản BNPL mới, chuẩn bị tiền cho các kỳ trả |
| 📑 Báo cáo | Biểu đồ theo thời gian/danh mục, ngân sách vs thực tế, tổng hợp BNPL, xuất CSV (UTF-8 có BOM, mở được bằng Excel) |
| ⚙️ Cài đặt | Số dư ban đầu, ngưỡng rủi ro, trạng thái AI, nạp demo/xóa dữ liệu |

## Quy tắc nghiệp vụ (quan trọng)

1. **Không tính trùng.** Giá trị đơn hàng BNPL *không* phải chi tiêu. Chỉ **tiền thực trả** vào chi tiêu thực tế: tiền trả trước và các khoản đã thanh toán cho từng kỳ (kể cả trả một phần). Giao dịch hằng ngày không cho chọn phương thức «BNPL» vì lý do này.
2. **Đã phát sinh ≠ dự kiến.** Chi tiêu thực tế chỉ gồm khoản có ngày ≤ hôm nay. Kỳ chưa trả, chi phí cố định chưa đến hạn, thu nhập chưa nhận chỉ xuất hiện trong dự báo.
3. **Số dư hiện tại ≠ số dư dự kiến.**
   - Số dư hiện tại = số dư ban đầu + thu nhập đã nhận − chi tiêu thực tế (kể từ ngày áp dụng số dư).
   - Số dư dự kiến cuối tháng = số dư hiện tại + thu nhập còn lại − chi phí cố định còn lại − kỳ BNPL phải trả (gồm cả kỳ quá hạn) − chi tiêu biến đổi ước tính còn lại.
4. **Hạn mức BNPL không phải tiền mặt** và không bao giờ được cộng vào số dư.
5. **Lịch trả góp:** tổng phải trả = trả trước + (giá trị đơn − trả trước + phí). Phần còn lại chia đều số kỳ (VNĐ nguyên), số lẻ cộng vào kỳ cuối; kỳ đến hạn cùng ngày mỗi tháng (tháng ngắn lấy ngày cuối tháng). *Phí là tổng phí cả kỳ hạn*, nhập thủ công theo thông tin của dịch vụ.
6. **Chi tiêu biến đổi ước tính** = trung bình tối đa 3 tháng gần nhất (chỉ giao dịch hằng ngày); chưa có lịch sử thì dùng ngân sách đã đặt (trừ phần chi phí cố định cùng danh mục); chưa có cả hai thì bằng 0 và ứng dụng nói rõ.
7. **Chi phí cố định** tự được tính là đã chi vào ngày trả hằng tháng (từ tháng áp dụng); không cần nhập lại ở mục Chi tiêu. Tạm dừng một chi phí sẽ bỏ cả các kỳ trong quá khứ của chi phí đó.
8. **Mức rủi ro** do Python tính bằng quy tắc minh bạch (hiển thị cạnh kết quả và chỉnh được ở Cài đặt):
   - *Rủi ro cao*: phải trả ngay nhiều hơn số dư hiện tại; hoặc số dư dự kiến cuối tháng nào đó < 0; hoặc (chi phí cố định + BNPL)/thu nhập tháng > 70%.
   - *Cần cân nhắc*: số dư dự kiến thấp nhất < mức đệm an toàn (mặc định 500.000 ₫); hoặc tỷ lệ nghĩa vụ > 50%.
   - *Rủi ro thấp*: không vi phạm các điều kiện trên.
   - *Chưa đủ dữ liệu*: chưa đặt số dư ban đầu hoặc chưa có nguồn thu nhập.

   Các ngưỡng là **tự thiết lập, không phải chuẩn tài chính chính thức**, không thay thế tư vấn chuyên môn.
9. **Guard AI** chỉ nhận số liệu do `guard/finance.py` tính; system prompt cấm bịa số hay tính lại/đổi các chỉ số đó.

## Cấu trúc mã nguồn

```
app.py                 điểm vào, điều hướng, sidebar
guard/
  finance.py           nghiệp vụ tài chính thuần Python/pandas (dễ kiểm thử)
  db.py                SQLite: schema, kiểm tra dữ liệu nhập, CRUD, nạp dữ liệu
  ai.py                ngữ cảnh số liệu + gọi API LLM (Anthropic / OpenAI-compatible)
  seed.py              dữ liệu demo
  ui/                  giao diện: styles, common, dashboard, budget, spending, bnpl, check, chat, reports, settings
tests/                 pytest: nghiệp vụ, CSDL, AI (mock HTTP), smoke test giao diện (AppTest)
```

## Kiểm thử

```bash
python -m pytest -q
```

Gồm kiểm thử phép tính tài chính (lịch trả góp, thanh toán một phần, chống tính trùng, dự báo, phân loại rủi ro, ngân sách, cảnh báo), kiểm tra dữ liệu nhập, lưu trữ SQLite, AI (giả lập HTTP, không gọi mạng thật) và chạy thử mọi trang cùng các thao tác thêm giao dịch/BNPL/thanh toán/kiểm tra mua.

## Giới hạn hiện tại

- Không đồng bộ trực tiếp với Shopee/SPayLater; mọi khoản BNPL nhập thủ công.
- Ứng dụng một người dùng, không có đăng nhập (dữ liệu nằm trong file SQLite cục bộ). Khi triển khai công khai cần thêm xác thực.
- Phí BNPL nhập dạng tổng số tiền; chưa mô hình hóa lãi suất/phí chậm trả theo ngày.
- «Hôm nay» tính theo múi giờ Asia/Ho_Chi_Minh.
