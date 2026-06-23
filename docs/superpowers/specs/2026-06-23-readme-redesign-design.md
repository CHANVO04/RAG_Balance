# Thiết kế Cải tiến README.md cho RAG Balance (SciHybrid-RAG)

Tài liệu thiết kế này phác thảo cách cấu trúc lại tệp `README.md` của dự án **RAG Balance** theo mô hình của dự án mã nguồn mở chất lượng cao (tham khảo cấu trúc của `LeDat98/NexusRAG`), giúp tăng tính chuyên nghiệp, trực quan và khoa học để thu hút người dùng đánh giá star.

---

## 1. Bản Đồ Cấu Trúc README.md Mới

README.md sẽ được tổ chức lại chi tiết như sau:

### 1.1. Tiêu đề và Badges (Đầu trang)
- Tên dự án: `# RAG Balance (SciHybrid-RAG)`
- Tagline: `Hệ thống Hybrid Graph-Vector RAG chuyên sâu cho tài liệu khoa học phức tạp`
- Các Badge:
  - `[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)`
  - `[![React 19](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)`
  - `[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)`
  - `[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)`
  - `[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)`

### 1.2. Trực quan hóa & Video (Showcase)
- Đặt video demo và ảnh sơ đồ kiến trúc hệ thống ở đầu:
  - Video: `### 🎥 [Xem Video Trực Quan Trên YouTube](https://www.youtube.com/watch?v=AkAaCEXnY_U)`
  - Ảnh sơ đồ kiến trúc: `![Sơ đồ kiến trúc RAG Balance](docs/assets/architecture.png)`

### 1.3. Bảng so sánh với RAG truyền thống (Beyond Traditional RAG)
| Khía cạnh | RAG Truyền Thống | RAG Balance |
| :--- | :--- | :--- |
| **Đọc & Trích xuất** | Đọc text trơn, mất bố cục cột/bảng/chương mục | Sử dụng **IBM Docling**: Giữ nguyên cấu trúc phân cấp, trang, bảng |
| **Công thức Toán** | Bỏ qua hoặc trích xuất lỗi | Cắt ảnh công thức $\rightarrow$ dùng **GPT-Vision** dịch sang LaTeX |
| **Ảnh & Bảng biểu** | Bỏ qua hoàn toàn | Crop ảnh $\rightarrow$ sinh caption $\rightarrow$ nhúng dạng vector vào `rag_visuals` |
| **Bộ Chunker** | Cắt theo kích thước cố định (breaks mid-sentence) | **Hybrid Chunker** thông minh: Gom cụm theo ngữ nghĩa + cấu trúc bài viết |
| **Phương thức Tìm kiếm** | Chỉ tìm kiếm Vector gần đúng (Vector Search) | **Lai 3 đường (Parallel)**: Vector (Qdrant) + Đồ thị 2-hop (Neo4j) + Reranker |
| **Đồ thị tri thức** | Không hỗ trợ | Trích xuất quan hệ thực thể $\rightarrow$ lưu Neo4j $\rightarrow$ truy vấn dạng 2-hop |
| **Trích dẫn nguồn** | Không có hoặc chỉ hiển thị tên file chung chung | Gắn mã trích dẫn ngẫu nhiên 4 ký tự $\rightarrow$ click tự động nhảy tới trang PDF |
| **Không gian làm việc** | Dùng chung toàn bộ cơ sở dữ liệu | **Workspace Isolation**: Tách biệt thư mục và phân vùng DB cho từng dự án |

### 1.4. Các Tính Năng Chi Tiết (Features)
Sử dụng thẻ `<details>` để người dùng click mở rộng/thu gọn giống NexusRAG:
- `<details><summary><b>Trích xuất tài liệu thông minh (IBM Docling)</b></summary>`
  - Hỗ trợ PDF, DOCX, PPTX, HTML.
  - Phân tích cấu trúc trang, giữ nguyên phân cấp chương mục (Header), danh sách (List).
- `<details><summary><b>Mắt thần dịch công thức & bảng biểu (VLM OCR)</b></summary>`
  - Tự động crop vùng chứa công thức toán học và dùng mô hình vision dịch sang mã LaTeX `$formula$`.
  - Đọc bảng dữ liệu phức tạp thành bảng Markdown, sinh tóm tắt nội dung để phục vụ tìm kiếm.
- `<details><summary><b>Tìm kiếm lai song song (Hybrid Retrieval)</b></summary>`
  - Nhúng vector 1536 chiều bằng `text-embedding-3-small` vào Qdrant.
  - Đồ thị tri thức Neo4j: Truy vấn quan hệ 2-hop bắt đầu từ các đỉnh được neo (anchored) bởi vector search, tránh đi lạc sang thông tin nhiễu.
  - Reranker Cross-Encoder `ms-marco-MiniLM-L-6-v2` chấm điểm lại ở chế độ Hybrid để tối ưu ngữ cảnh.
- `<details><summary><b>Đồng bộ trang PDF khi click nguồn trích dẫn</b></summary>`
  - Mọi câu trả lời có mã nguồn (ví dụ `[a3z1]` hoặc `[IMG-p4f2]`).
  - Giao diện 3-pane tự động đồng bộ: click vào nguồn sẽ cuộn iframe PDF gốc đúng số trang và vị trí phần tử.
- `<details><summary><b>Cô lập Workspace đa người dùng (Workspace Isolation)</b></summary>`
  - Dữ liệu tệp tải lên lưu tại `backend/workspaces/{workspace_id}/data/`.
  - Đăng ký tài liệu và cache cục bộ lưu tại `backend/workspaces/{workspace_id}/db/`.
  - Bộ lọc Qdrant hoạt động dựa trên trường `workspace_id`.

### 1.5. Hướng dẫn chạy nhanh (Quick Start)
- Giữ nguyên các phần tiếng Việt cũ:
  - Những thứ cần chuẩn bị sẵn trên máy tính (Docker, Node.js, Python, OpenAI API Key).
  - Các bước cài đặt và khởi chạy dự án (clone, điền `.env`, bật Docker compose cho Qdrant/Neo4j, chạy `.\run_dev.bat` để tự động hóa setup và khởi chạy).
  - Cách truy cập vào ứng dụng (cổng 5173, 8000/docs, 6333/dashboard, 7474).
  - Cấu trúc thư mục của dự án (mô tả rõ backend, frontend, setup.bat, run_dev.bat).
  - Mẹo cài đặt nhanh nếu máy mạng yếu hoặc không có card đồ họa GPU (sử dụng pip install torch CPU-only).

### 1.6. Danh sách công nghệ (Tech Stack)
Trình bày dưới dạng bảng rõ ràng bao gồm:
- **Frontend UI**: React 19, Vite, TypeScript, Zustand, D3.js (Force graph), Tailwind CSS.
- **Backend API**: FastAPI, Python 3.10+, Uvicorn, SSE.
- **Vector DB**: Qdrant (Docker).
- **Graph DB**: Neo4j (Docker, Cypher queries).
- **AI/ML Engine**: IBM Docling, text-embedding-3-small, ms-marco Reranker, GPT-4.1-mini.

### 1.7. Các câu hỏi thường gặp (FAQ) & Kế hoạch (Roadmap)
- Giữ các lỗi trùng cổng, lỗi Docker, lỗi API Key từ README gốc.
- Roadmap: Hỗ trợ Ollama cục bộ (gemma4, qwen3.5), hoàn thiện tính năng cô lập đồ thị Neo4j chi tiết cho từng người dùng, tích hợp RAGAS đánh giá offline.

---

## 2. Sơ đồ kiến trúc Mermaid (Architecture Flow)
Chúng ta sẽ nhúng trực tiếp sơ đồ Mermaid của luồng nạp (Ingest Flow) và luồng truy vấn (Query Flow) vào README.md để làm tài liệu khoa học trực quan.

---

## 3. Kế hoạch kiểm thử (Verification)
- Kiểm tra hiển thị Markdown của các thẻ `<details>`, bảng so sánh, và Mermaid.
- Đảm bảo các liên kết file ảnh sơ đồ (`docs/assets/architecture.png`) hoạt động bình thường.
