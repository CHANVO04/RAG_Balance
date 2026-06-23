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
Sử dụng thẻ `<details>` để người dùng click mở rộng/thu gọn giống NexusRAG. Các tính năng được trích xuất chính xác 100% từ codebase:

1. `<details><summary><b>1. Trích xuất tài liệu thông minh (IBM Docling)</b></summary>`
   - Đọc và hiểu bố cục các file PDF, DOCX, PPTX, HTML phức tạp.
   - Nhận diện đúng cấu trúc phân cấp (Header 1, Header 2, List items) để không làm mất mạch văn bản khi cắt nhỏ.
   - Trích xuất bảng biểu trực tiếp thành bảng Markdown hoàn chỉnh.

2. `<details><summary><b>2. Mắt thần dịch công thức & bảng biểu (VLM OCR)</b></summary>`
   - Nhận diện vùng chứa công thức toán học dưới dạng ảnh, tự động gọi Vision LLM (mặc định gpt-4.1-mini) dịch thành mã LaTeX dạng `$formula$`.
   - Cắt ảnh sơ đồ, biểu đồ hoặc hình vẽ, dùng Vision model để viết mô tả chi tiết (caption) và lưu giữ vị trí (tọa độ trang) của ảnh đó.
   - Nhúng phần mô tả và công thức LaTeX này trực tiếp vào các chunk chữ xung quanh dưới nhãn `VISUAL ENRICHMENT` giúp tìm kiếm vector dễ dàng quét trúng.

3. `<details><summary><b>3. Cắt nhỏ văn bản thông minh & Tránh trùng lặp (Hybrid Chunker & Registry)</b></summary>`
   - Sử dụng bộ đếm Tokenizer cl100k_base (đồng bộ với OpenAI) để gom văn bản thành các đoạn tối đa 512 tokens mà không cắt nửa chừng câu.
   - Tích hợp bộ đăng ký (registry.json) để tính toán mã hash SHA-256 của từng file. Nếu file đã tải lên trước đó, hệ thống sẽ bỏ qua, tránh nạp trùng lặp tốn dung lượng và chi phí API.
   - Lọc bỏ các khối trùng lặp gần nhau (near-deduplication) dựa trên so sánh chữ mở đầu của đoạn.

4. `<details><summary><b>4. Tìm kiếm lai kết hợp Đồ thị (Hybrid retrieval: Qdrant + Neo4j)</b></summary>`
   - Nhúng văn bản thành vector 1536 chiều bằng mô hình `text-embedding-3-small` rồi lưu vào Qdrant (phân vùng `rag_docs` cho chữ và `rag_visuals` cho ảnh/bảng).
   - Đồ thị tri thức (Neo4j): Không tìm kiếm mù quáng, hệ thống sẽ lấy các chunk vector tìm thấy làm điểm neo (anchors), từ đó quét đồ thị xung quanh trong phạm vi 2-hop (Cypher query) để tìm các mối quan hệ thực thể liên quan trực tiếp.
   - Tích hợp bộ chấm điểm lại Cross-Encoder (`ms-marco-MiniLM-L-6-v2`) để sắp xếp lại độ ưu tiên ngữ cảnh trước khi gửi tới LLM.

5. `<details><summary><b>5. Bộ nhớ đệm câu trả lời ngữ nghĩa (Semantic Cache)</b></summary>`
   - Lưu trữ các câu hỏi và câu trả lời cũ vào một cơ sở dữ liệu đệm.
   - Khi có câu hỏi mới, hệ thống so sánh độ tương đồng vector của câu hỏi mới với các câu hỏi cũ trong cache. Nếu độ tương đồng vượt quá mức cấu hình (mặc định 0.87), hệ thống trả về câu trả lời có sẵn ngay lập tức mà không cần gọi GPT hay tra cứu DB, giúp tiết kiệm tiền API và trả lời trong 0.1 giây.

6. `<details><summary><b>6. Không gian làm việc riêng biệt (Workspace Isolation)</b></summary>`
   - Mỗi người dùng hoặc dự án có một Workspace riêng (mặc định là `default`).
   - File tải lên được cô lập hoàn toàn tại thư mục `backend/workspaces/{workspace_id}/data/`.
   - Cơ sở dữ liệu đăng ký và lưu trữ tệp nằm riêng biệt tại `backend/workspaces/{workspace_id}/db/`.
   - Các bản ghi vector trong Qdrant được phân mảnh và lọc bằng thuộc tính `workspace_id` để tránh dữ liệu bị lẫn lộn giữa các workspace.

7. `<details><summary><b>7. Đồng bộ nguồn trích dẫn và tài liệu gốc (Citation & PDF Sync)</b></summary>`
   - Gắn mã trích dẫn ngẫu nhiên 4 ký tự ngắn gọn (ví dụ `[a3z1]` cho text, hoặc `[IMG-p4f2]`, `[FORM-t2y1]` cho hình ảnh/công thức).
   - Giao diện 3 phân vùng (3-pane layout) liên kết chặt chẽ: khi người dùng nhấp chuột vào một mã trích dẫn trong câu trả lời, trình xem PDF ở khung bên cạnh sẽ tự động cuộn đến đúng số trang và vị trí của đoạn văn bản/hình ảnh được trích dẫn.

8. `<details><summary><b>8. Bản đồ phân cụm tài liệu 2D (UMAP Chunk Visualization)</b></summary>`
   - Gọi thuật toán giảm chiều dữ liệu UMAP để chiếu các vector chunk 1536 chiều xuống không gian 2 chiều `(x, y)`.
   - Hiển thị bản đồ phân bố các mảnh tài liệu trực quan trên giao diện web giúp người dùng thấy được mối quan hệ phân bố ngữ nghĩa giữa các chương mục bài viết.

9. `<details><summary><b>9. Trực quan hóa đồ thị tri thức tương tác (Interactive Knowledge Graph)</b></summary>`
   - Vẽ sơ đồ mạng lưới thực thể khoa học thực tế bằng React Flow/D3.js từ dữ liệu quét thực thể của Neo4j.
   - Hỗ trợ kéo thả, phóng to thu nhỏ, nhấp chọn đỉnh (node) để xem các mối quan hệ liên kết và xem các đoạn văn bản chứng cứ hỗ trợ.

10. `<details><summary><b>10. Kiểm soát chi phí & Theo dõi luồng suy nghĩ (SSE Observability & Token Budgeting)</b></summary>`
    - Server-Sent Events (SSE) giúp đẩy tiến trình thực tế xuống giao diện theo thời gian thực (Status $\rightarrow$ Thought $\rightarrow$ Early Sources $\rightarrow$ Tokens $\rightarrow$ Done).
    - Hiển thị hộp thoại "Luồng suy nghĩ" (Thought) để lập trình viên quan sát được các thông số tìm kiếm, cấu hình LLM trực tiếp.
    - Bộ đếm và cắt gọn token tự động (`_enforce_input_token_budget`) giúp đảm bảo không bao giờ gửi quá giới hạn cửa sổ ngữ cảnh đầu vào của mô hình OpenAI, tránh lỗi hệ thống và tiết kiệm chi phí gọi API.

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
