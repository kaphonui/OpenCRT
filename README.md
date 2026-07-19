# OpenCRT PySide6 v0.3

Sửa hai lỗi workflow của v0.2:

- Search tự bung thư mục và tự chọn kết quả đầu tiên.
- Gõ từ khóa rồi nhấn **Enter** để kết nối ngay.
- Nhấn **Down** trong ô search để chuyển sang danh sách kết quả.
- Nhấn **Esc** để xóa search.
- Sau khi mở kết nối, focus tự chuyển vào terminal nên gõ lệnh được ngay.
- Sửa Ctrl+V dùng clipboard hệ thống.
- Vẫn có SSH / Telnet / Serial, import SecureCRT, log, sidebar và tab.

## Chạy

Double-click `RUN_OPENCRT.bat`.

Nếu đang có môi trường `.venv` từ v0.2, bản v0.3 vẫn tự dùng bình thường.

## Build EXE

Double-click `BUILD_EXE.bat`.

## Search nhanh

1. Click ô Search.
2. Gõ tên hoặc IP.
3. Kết quả đầu tiên được chọn tự động.
4. Nhấn Enter để kết nối.
5. Sau khi login, con trỏ tự chuyển vào terminal.

## Lưu ý

Password chỉ lưu khi tick Remember và hiện lưu plain text. ANSI/VT100 vẫn mới ở mức cơ bản.
