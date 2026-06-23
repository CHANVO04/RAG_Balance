# Thiết kế Cải tiến README.md cho RAG Balance (SciHybrid-RAG)

Tài liệu thiết kế này phác thảo cách cấu trúc lại tệp `README.md` của dự án **RAG Balance** theo mô hình cấu trúc của dự án mã nguồn mở chất lượng cao (tham khảo từ `LeDat98/NexusRAG`), giúp tăng tính chuyên nghiệp, trực quan và khoa học để thu hút người dùng đánh giá star.

---

## 1. Nội dung thay đổi đề xuất

Chúng ta sẽ tái cấu trúc `README.md` thành các phần chính sau:

### 1.1. Phần đầu trang (Header & Badges)
- Giữ tên dự án: `# RAG Balance (SciHybrid-RAG)`
- Tagline: `Hệ thống Hybrid Graph-Vector RAG chuyên sâu cho tài liệu khoa học phức tạp`
- Các Badge định dạng `for-the-badge` hiện đại:
  - Python (3.10+)
  - React (19)
  - FastAPI
  - Docker (Required)
  - License (MIT)
- Câu kêu gọi hành động: "Tải tài liệu PDF/Word lên. Trích xuất bảng biểu & dịch công thức toán học. Trả lời kèm trích dẫn trang PDF gốc."
- Các liên kết điều hướng nhanh:
  ```markdown
  [Tính năng](#tính-năng-nổi-bật) · [So sánh](#điểm-vượt-trội-so-với-rag-truyền-thống) · [Kiến trúc](#kiến-trúc-hệ-thống) · [Khởi chạy nhanh](#hướng-dẫn-chạy-nhanh) · [Công nghệ](#các-công-nghệ-khoa-học-chính-được-sử-dụng)
  ```

### 1.2. Trực quan hóa & Video (Showcase)
- Khôi phục link video YouTube và ảnh giao diện chính (`docs/assets/image.png`) ngay dưới tiêu đề.
  - Video link: `### 🎥 [Xem Video Trực Quan Trên YouTube](https://www.youtube.com/watch?v=AkAaCEXnY_U)`
  - Ảnh demo: `![Giao diện chính](docs/assets/image.png)`

### 1.3. Điểm vượt trội so với RAG truyền thống (Beyond Traditional RAG)
- Bổ sung bảng so sánh trực quan để người dùng thấy tính feasibility (khả thi) của dự án.
- So sánh các khía cạnh: Đọc tài liệu (Docling), Công thức & Bảng biểu (VLM OCR), Chunker, Vector DB (Qdrant), Đồ thị tri thức (Neo4j), Trích dẫn (Citaitons & Page sync), Cách ly dữ liệu (Workspace Isolation).

### 1.4. Tính năng nổi bật (Features)
- Sử dụng thẻ `<details>` để người đọc có thể nhấn mở rộng/thu gọn từng tính năng, giúp README gọn gàng và dễ đọc.
- Các nhóm tính năng bao gồm:
  - Trích xuất văn bản thông minh (IBM Docling)
  - Mắt thần dịch công thức & bảng biểu (VLM OCR)
  - Tìm kiếm lai 3 đường song song (Hybrid Retrieval)
  - Đồng bộ trang PDF khi click nguồn trích dẫn
  - Không gian làm việc riêng biệt (Workspace Isolation)

### 1.5. Kiến trúc hệ thống (Architecture)
- Nhúng các sơ đồ Mermaid biểu diễn luồng nạp dữ liệu (Ingest Flow) và luồng hỏi đáp (Query Flow) từ file `AGENTS.md` để giải thích mặt kỹ thuật khoa học của dự án.

### 1.6. Hướng dẫn chạy nhanh (Quick Start)
Giữ nguyên toàn bộ nội dung hướng dẫn tiếng Việt chi tiết từ README cũ bao gồm:
- Những thứ cần chuẩn bị sẵn trên máy tính
- Các bước cài đặt và khởi chạy dự án
- Cách truy cập vào ứng dụng
- Cấu trúc thư mục của dự án
- Mẹo cài đặt nhanh nếu máy mạng yếu hoặc không có card đồ họa GPU

### 1.7. Các công nghệ khoa học chính được sử dụng (Tech Stack)
- Trình bày dạng bảng hoặc danh sách chuẩn hóa về các công nghệ: IBM Docling, Qdrant, Neo4j, OpenAI.

### 1.8. Các câu hỏi thường gặp (FAQ) & Kế hoạch phát triển (Roadmap)
- Các lỗi thường gặp: Lỗi trùng cổng, lỗi Docker, lỗi API Key.
- Kế hoạch phát triển tiếp theo được tinh chỉnh thực tế: hỗ trợ LLM chạy offline (Ollama/Gemini), tối ưu đồ thị Neo4j cho từng user, tích hợp công cụ đánh giá tự động (RAGAS).

---

## 2. Quy tắc ngôn ngữ
- Giữ nguyên văn phong tiếng Việt tự nhiên, trực diện, không dùng từ ngữ phóng đại của AI (tránh từ như "cách mạng hóa", "vô tiền khoáng hậu").
- Các hướng dẫn thao tác nút bấm giữ nguyên ngôn ngữ thuần phác như bản gốc.

---

## 3. Kế hoạch kiểm thử (Verification)
- Đảm bảo cú pháp Markdown hiển thị đúng (kiểm tra các thẻ đóng mở `<details>`).
- Kiểm tra các liên kết hình ảnh và sơ đồ Mermaid render không lỗi.
