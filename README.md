# RAG Balance (SciHybrid-RAG)

Dự án này là một phần mềm giúp bạn tải các bài báo khoa học lên (file PDF hoặc Word) và chat hỏi đáp với chúng. 

Điểm khác biệt của phần mềm này so với các công cụ chat PDF thông thường là nó không chỉ đọc chữ, mà còn tự động nhận diện các bảng biểu, hình ảnh và dịch các công thức toán học từ dạng ảnh sang dạng chữ (chữ LaTeX) để lưu lại. Nó sử dụng kết hợp hai loại cơ sở dữ liệu là Vector DB (Qdrant) để tìm kiếm nhanh và Đồ thị tri thức (Neo4j) để tìm các mối liên hệ sâu giữa các định nghĩa khoa học.

---

## Những thứ cần chuẩn bị sẵn trên máy tính

Trước khi bắt đầu chạy, máy tính của bạn bắt buộc phải có sẵn các phần mềm sau:
1. **Docker Desktop**: Cần thiết để khởi động các cơ sở dữ liệu Qdrant và Neo4j. Hãy chắc chắn rằng bạn đã mở Docker Desktop lên trước khi chạy dự án.
2. **Node.js** (Phiên bản 20 hoặc mới hơn): Cần để chạy giao diện React.
3. **Python** (Phiên bản 3.10 hoặc mới hơn): Cần để chạy code xử lý dữ liệu backend.
4. **OpenAI API Key**: Cần có một khóa API của OpenAI (để gọi mô hình GPT dịch công thức và trả lời câu hỏi).

---

## Các bước cài đặt và khởi chạy dự án

Bạn chỉ cần thực hiện đúng các bước sau đây là dự án sẽ chạy được trên mọi máy tính Windows:

### Bước 1: Tải mã nguồn về máy
Bạn tiến hành clone dự án này từ GitHub về thư mục trên máy tính của mình.

### Bước 2: Tạo file cấu hình và điền API Key
1. Bạn vào thư mục `backend/`.
2. Tìm file tên là `.env.example`.
3. Tạo một bản sao của file đó và đổi tên thành `.env`.
4. Mở file `.env` đó lên bằng Notepad hoặc VS Code.
5. Tìm dòng `OPENAI_API_KEY=sk-your-openai-api-key-here` và thay thế đoạn `sk-your-openai-api-key-here` bằng API key thật của bạn. Lưu file lại.

### Bước 3: Khởi động các cơ sở dữ liệu (Docker)
Mở terminal (như Command Prompt hoặc PowerShell) lên, di chuyển vào thư mục dự án và chạy các lệnh sau:

1. Chạy cơ sở dữ liệu Vector Qdrant:
   ```cmd
   cd backend/qdrant-server
   docker compose up -d
   ```
2. Chạy cơ sở dữ liệu Đồ thị Neo4j:
   ```cmd
   cd ../neo4j-server
   docker compose up -d
   ```
   *(Tài khoản mặc định của Neo4j là: Username: `neo4j` | Password: `rag_password`)*

### Bước 4: Chạy dự án (Chỉ cần 1 câu lệnh duy nhất)
Quay trở lại thư mục gốc của dự án (thư mục `A_RAG_MAIN`), mở terminal và gõ lệnh sau:
```cmd
.\run_dev.bat
```
**Lưu ý quan trọng ở lần đầu tiên chạy:**
* Khi bạn chạy lệnh này lần đầu tiên, file `.bat` sẽ tự động phát hiện máy bạn chưa cài đặt môi trường. Nó sẽ tự động gọi file `setup.bat` để cài đặt thư viện cho React và tạo môi trường ảo Python cho Backend.
* Quá trình này sẽ mất khoảng vài phút vì máy tính phải tải thư viện PyTorch khá nặng (~1.5GB đến 2GB). Hãy kiên nhẫn đợi cho đến khi nó chạy xong.
* Từ lần thứ 2 trở đi, lệnh này sẽ bỏ qua bước cài đặt và khởi động luôn giao diện + backend chỉ trong vòng 1 giây.

---

## Cách truy cập vào ứng dụng

Khi terminal chạy xong và báo thành công, bạn mở trình duyệt web lên và truy cập các địa chỉ sau:
* **Giao diện người dùng (React)**: http://localhost:5173
* **Trang quản trị Backend (FastAPI)**: http://localhost:8000/docs (Trang này dùng để xem các cổng API hoạt động thế nào)
* **Trang quản trị Vector Qdrant**: http://localhost:6333/dashboard
* **Trang quản trị Đồ thị Neo4j**: http://localhost:7474

---

## Cấu trúc thư mục của dự án

Dưới đây là sơ đồ các thư mục chính để bạn dễ hình dung:
* `backend/`: Chứa toàn bộ code xử lý logic, đọc file PDF, trích xuất dữ liệu và trả lời câu hỏi.
  * `ingest/`: Code để đọc file PDF, dịch công thức, cắt nhỏ văn bản và lưu vào cơ sở dữ liệu.
  * `query/`: Code để tìm kiếm thông tin và gọi GPT trả lời.
  * `qdrant-server/` và `neo4j-server/`: Cấu hình Docker để chạy cơ sở dữ liệu.
  * `main.py`: File chạy chính của server backend.
  * `requirements.txt`: Danh sách các thư viện Python cần cài.
* `frontend/react-app/`: Chứa giao diện web để người dùng thao tác bấm nút, tải file và chat.
* `setup.bat`: File tự động cài đặt thư viện cho dự án ở lần đầu tiên.
* `run_dev.bat`: File chính dùng để khởi chạy dự án hàng ngày.

---

## Mẹo cài đặt nhanh nếu máy mạng yếu hoặc không có card đồ họa GPU

Vì thư viện PyTorch mặc định tải về bản có hỗ trợ card đồ họa CUDA rất nặng (~2GB), nếu máy tính của bạn không có card đồ họa rời hoặc muốn tải nhanh hơn gấp 10 lần, bạn hãy làm như sau trước khi chạy file bat:
1. Mở terminal tại thư mục gốc của dự án.
2. Tạo môi trường ảo Python và kích hoạt nó:
   ```cmd
   cd backend
   python -m venv venv
   call venv\Scripts\activate
   ```
3. Chạy lệnh cài đặt phiên bản PyTorch CPU-only (bản này chỉ nặng khoảng 150MB):
   ```cmd
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   ```
4. Sau đó bạn quay lại thư mục gốc và chạy file `.\run_dev.bat` như bình thường. Hệ thống sẽ tự động cài các thư viện còn lại mà không tải lại bản PyTorch nặng nữa.

---

## Các công nghệ khoa học chính được sử dụng

Nếu bạn muốn tìm hiểu sâu hoặc trích dẫn các tài liệu khoa học làm nền tảng cho dự án này, dưới đây là các công nghệ cốt lõi:
1. **IBM Docling**: Thư viện phân tích cấu trúc tài liệu PDF nâng cao của IBM, giúp phân đoạn văn bản thông minh mà không bị mất cấu trúc chương mục.
2. **Qdrant**: Cơ sở dữ liệu Vector hiệu năng cao dùng để lưu trữ và tìm kiếm tương đồng cho văn bản và các thành phần trực quan.
3. **Neo4j**: Cơ sở dữ liệu Đồ thị giúp lưu giữ thực thể khoa học và các liên kết tri thức phục vụ cho việc suy luận ngữ nghĩa (GraphRAG).
4. **OpenAI text-embedding-3-small & GPT-4.1-mini**: Các mô hình nhúng ngôn ngữ và xử lý đa phương thức (Vision) để nhận diện công thức, bảng biểu và sinh câu trả lời.

