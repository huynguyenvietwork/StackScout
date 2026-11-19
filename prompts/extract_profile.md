Bạn là chuyên gia phân tích tech stack. Hãy xây dựng hồ sơ kỹ năng
của tôi từ [mã nguồn trong thư mục hiện tại / CV bên dưới].

Nếu quét mã nguồn, hãy đọc các file khai báo phụ thuộc và cấu hình:
*.csproj, Directory.Packages.props, package.json, requirements.txt,
pyproject.toml, go.mod, Cargo.toml, Dockerfile, docker-compose.yml,
.github/workflows/*, *.tf, cấu hình Kubernetes.

Quy tắc:
- Chỉ ghi những gì có bằng chứng trong mã nguồn hoặc CV.
- Bảo mật: CHỈ ghi tên công nghệ, công cụ, framework và mức độ.
  Không ghi tên dự án, repo, sản phẩm, công ty, khách hàng, dự án dùng
  để làm gì, tên người, URL, máy chủ hay thông tin hạ tầng.
- Bỏ qua thư viện phụ thuộc gián tiếp và tiện ích quá nhỏ.
- Gộp các gói cùng một công nghệ (Microsoft.EntityFrameworkCore.*
  là "Entity Framework Core").
- Tên công nghệ viết chuẩn, không kèm số phiên bản.
- level: advanced nếu dùng ở nhiều nơi hoặc cấu hình sâu,
  intermediate nếu dùng rõ ràng, beginner nếu chỉ thoáng qua.
- category CHỈ được chọn trong danh sách sau:
  [language, runtime, web-backend-framework, web-frontend-framework,
   meta-framework, orm-data-access, database-sql, database-nosql,
   vector-db, cache, message-queue, background-jobs, api-tooling,
   auth-identity, testing, build-tooling, ci-cd, containers, iac,
   cloud-platform, logging-observability, llm-provider-sdk,
   agent-framework, agent-protocol, rag-retrieval, ai-coding-tool,
   local-llm-inference, data-processing, other]
- ecosystem CHỈ chọn trong: dotnet, node, python, jvm, go, rust,
  frontend, mobile, cloud, any.

Chỉ trả về YAML đúng cấu trúc sau, không giải thích thêm:

person:
  role: ""
  interests: []
skills:
  - name: ""
    category: ""
    ecosystem: ""
    level: ""
