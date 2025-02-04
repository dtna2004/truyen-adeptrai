# Ứng Dụng Tạo Truyện Ma Tự Động

Ứng dụng này sử dụng API của Google Gemini để tạo ra các câu chuyện ma tự động dựa trên gợi ý của người dùng. Bao gồm cả giao diện quản lý và website để đọc truyện.

## Tính năng

1. Tạo truyện tự động:
   - Tạo khung truyện từ ý tưởng
   - Tự động tạo nội dung các chương
   - Hỗ trợ truyện nhiều chương (lên đến 2000 chương)

2. Quản lý truyện:
   - Xem danh sách truyện
   - Xóa truyện
   - Xuất truyện ra file Word
   - Đẩy truyện lên website

3. Website đọc truyện:
   - Xem danh sách truyện mới
   - Xem truyện đã hoàn thành
   - Đọc từng chương
   - Giao diện thân thiện, responsive

## Cài đặt

1. Clone repository:
```bash
git clone https://github.com/dtna2004/truyen-adeptrai.git
cd truyen-adeptrai
```

2. Tạo môi trường ảo và cài đặt thư viện:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

3. Cấu hình API key:
- Thêm API key của Google Gemini vào file `ghost_story_generator.py`

## Chạy ứng dụng

1. Chạy Streamlit app (giao diện quản lý):
```bash
streamlit run ghost_story_generator.py
```

2. Chạy Flask server (website):
```bash
python app.py
```

3. Truy cập:
- Giao diện quản lý: http://localhost:8501
- Website đọc truyện: http://localhost:5000

## Công nghệ sử dụng

- Python
- Streamlit
- Flask
- Google Gemini API
- SQLite
- HTML/CSS/JavaScript

## Đóng góp

Mọi đóng góp đều được hoan nghênh! Vui lòng tạo issue hoặc pull request.

## Cách sử dụng

1. Mở trình duyệt và truy cập địa chỉ được hiển thị sau khi chạy lệnh (thường là http://localhost:8501)
2. Nhập gợi ý cho câu chuyện ma của bạn vào ô văn bản
3. Chọn độ dài mong muốn cho câu chuyện (ngắn, trung bình, dài)
4. Nhấn nút "Tạo Truyện Ma" và đợi hệ thống tạo ra câu chuyện

## Lưu ý

- Mỗi lần tạo sẽ cho ra một câu chuyện khác nhau, ngay cả khi sử dụng cùng một gợi ý
- Thời gian tạo truyện có thể thay đổi tùy thuộc vào độ dài được chọn
- Nội dung truyện được tạo ra hoàn toàn tự động và có thể không phù hợp với mọi độ tuổi 