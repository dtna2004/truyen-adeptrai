import streamlit as st
import requests
import json
import os
import sqlite3
from datetime import datetime
import uuid
import re
from docx import Document
from fpdf import FPDF
import tempfile

# Cấu hình API
API_KEYS = [
    "AIzaSyA6-W9fSgwDFSjf2i-gnirXwfaiah6M2zg",
    "AIzaSyC7lFa-0ZHvh09Hm4TtYfVc894UQXggLX0",
    "AIzaSyBWS4VBDtvkkbkvZyaawUbWAle4sXPS7YU",
    "AIzaSyAiAXsuJ9o1bCjaaRh2aUUYaTiZIFvU0Co",
    "AIzaSyDqESoT7B7CIkxfLBdC3DzbgjxbSVjq36o"
    # Thêm các API key khác vào đây
]
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

# Khởi tạo SQLite database
def init_db():
    conn = sqlite3.connect('ghost_stories.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stories
                 (story_id TEXT PRIMARY KEY, outline TEXT, original_prompt TEXT, 
                  created_at TIMESTAMP, last_updated TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chapters
                 (chapter_id TEXT PRIMARY KEY, story_id TEXT, chapter_number INTEGER,
                  content TEXT, created_at TIMESTAMP,
                  FOREIGN KEY (story_id) REFERENCES stories(story_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS chapter_versions
                 (version_id TEXT PRIMARY KEY, chapter_id TEXT, content TEXT,
                  created_at TIMESTAMP,
                  FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS story_arcs
                 (arc_id TEXT PRIMARY KEY, story_id TEXT, arc_number INTEGER,
                  outline TEXT, created_at TIMESTAMP,
                  FOREIGN KEY (story_id) REFERENCES stories(story_id))''')
    conn.commit()
    conn.close()

# Gọi hàm khởi tạo database khi khởi động ứng dụng
init_db()

def get_db():
    return sqlite3.connect('ghost_stories.db')

# Biến đếm để theo dõi API key hiện tại
current_api_key_index = 0

def get_next_api_key():
    global current_api_key_index
    api_key = API_KEYS[current_api_key_index]
    current_api_key_index = (current_api_key_index + 1) % len(API_KEYS)
    return api_key

def call_api(messages, max_tokens=1000, retry_count=3):
    global current_api_key_index
    
    for _ in range(retry_count):
        try:
            api_key = get_next_api_key()
            prompt = ""
            for msg in messages:
                if msg["role"] == "system":
                    prompt += f"Instructions: {msg['content']}\n\n"
                else:
                    prompt += f"{msg['content']}\n"

            data = {
                "contents": [{
                    "parts":[{"text": prompt}]
                }],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.7,
                    "topP": 0.95,
                },
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            }

            response = requests.post(
                f"{API_URL}?key={api_key}",
                headers={"Content-Type": "application/json"},
                json=data,
                timeout=60
            )
            response_json = response.json()
            
            if response.status_code != 200:
                error_message = response_json.get('error', {}).get('message', 'Unknown error')
                if "quota" in error_message.lower():
                    # Nếu hết quota, thử API key tiếp theo
                    continue
                st.error(f"Lỗi: {error_message}")
                return f"Lỗi: {error_message}"

            if 'candidates' in response_json:
                return response_json['candidates'][0]['content']['parts'][0]['text']
            
        except Exception as e:
            st.error(f"Lỗi: {str(e)}")
            # Thử API key tiếp theo nếu có lỗi
            continue
    
    return "Không thể tạo nội dung. Vui lòng thử lại sau."

def search_stories(query):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT story_id, outline, created_at FROM stories
                 WHERE outline LIKE ? OR original_prompt LIKE ?''',
              (f'%{query}%', f'%{query}%'))
    results = c.fetchall()
    conn.close()
    return [{"story_id": r[0], "outline": r[1], "created_at": datetime.fromisoformat(r[2])} for r in results]

def rewrite_story(content, style="normal"):
    styles = {
        "normal": "Viết lại đoạn văn sau với cách diễn đạt mới nhưng giữ nguyên nội dung chính:",
        "creative": "Viết lại đoạn văn sau một cách sáng tạo hơn, thêm các chi tiết mới thú vị:",
        "simple": "Viết lại đoạn văn sau một cách đơn giản, dễ hiểu hơn:",
        "detailed": "Viết lại đoạn văn sau với nhiều chi tiết hơn về cảm xúc và môi trường:"
    }
    
    messages = [
        {"role": "system", "content": "Bạn là một nhà văn chuyên viết truyện ma kinh dị."},
        {"role": "user", "content": f"{styles[style]}\n\n{content}"}
    ]
    return call_api(messages, max_tokens=len(content.split()) + 200)

def generate_story_outline(prompt, num_chapters=10):
    messages = [
        {"role": "system", "content": f"""Bạn là một nhà văn chuyên viết truyện ma kinh dị. 
        Hãy tạo một khung truyện chi tiết bằng tiếng Việt, bao gồm:
        1. Tên truyện
        2. Thể loại
        3. Giới thiệu ngắn (1-2 đoạn)
        4. Nhân vật chính:
           - Tên và vai trò
           - Đặc điểm ngoại hình và tính cách
        5. Bối cảnh:
           - Thời gian và không gian
           - Không khí và màu sắc truyện
        6. Cốt truyện chính:
           - Điểm khởi đầu
           - Các tình tiết chính
           - Cao trào
           - Kết thúc
        7. Số phần dự kiến và nội dung chính của mỗi phần
        8. Danh sách {num_chapters} chương cho phần 1:
           (Mỗi chương phải có:
           - Tên chương rõ ràng
           - Tóm tắt nội dung chính 2-3 câu)"""},
        {"role": "user", "content": prompt}
    ]
    return call_api(messages, max_tokens=2000)

def generate_arc_outline(story_outline, arc_number, num_chapters):
    # Tạo outline cho một phần cụ thể của truyện
    messages = [
        {"role": "system", "content": f"""Bạn là một nhà văn chuyên viết truyện ma kinh dị.
        Dựa vào khung truyện sau:
        {story_outline}
        
        Hãy tạo outline chi tiết cho phần {arc_number}, bao gồm:
        1. Tên phần
        2. Mục tiêu của phần này trong cốt truyện tổng thể
        3. Các tình tiết chính cần đạt được
        4. Danh sách {num_chapters} chương:
           (Mỗi chương phải có:
           - Tên chương rõ ràng
           - Tóm tắt nội dung chính 2-3 câu)"""}
    ]
    return call_api(messages, max_tokens=1500)

def generate_chapter(chapter_outline, story_outline, chapter_number, total_chapters, word_count):
    messages = [
        {"role": "system", "content": f"""Bạn là một nhà văn chuyên viết truyện ma kinh dị.
        Hãy viết chương {chapter_number}/{total_chapters} với độ dài khoảng {word_count} từ.
        Dựa vào khung truyện sau:
        {story_outline}
        
        Yêu cầu:
        - Đảm bảo tính liên kết với các chương trước/sau
        - Phát triển tình tiết theo đúng cốt truyện
        - Xây dựng không khí rùng rợn
        - Miêu tả chi tiết cảm xúc nhân vật
        - Tạo ra những tình tiết bất ngờ nhưng hợp lý
        - Kết hợp đối thoại và miêu tả
        """},
        {"role": "user", "content": f"Viết chương {chapter_number} dựa trên outline: {chapter_outline}"}
    ]
    return call_api(messages, max_tokens=word_count * 2)

def save_story_outline(outline, prompt):
    conn = get_db()
    c = conn.cursor()
    story_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    c.execute('''INSERT INTO stories (story_id, outline, original_prompt, created_at, last_updated)
                 VALUES (?, ?, ?, ?, ?)''', (story_id, outline, prompt, now, now))
    conn.commit()
    conn.close()
    return story_id

def save_arc_outline(story_id, arc_number, outline):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    
    # Thêm bảng story_arcs nếu chưa có
    c.execute('''CREATE TABLE IF NOT EXISTS story_arcs
                 (arc_id TEXT PRIMARY KEY, story_id TEXT, arc_number INTEGER,
                  outline TEXT, created_at TIMESTAMP,
                  FOREIGN KEY (story_id) REFERENCES stories(story_id))''')
    
    arc_id = str(uuid.uuid4())
    c.execute('''INSERT INTO story_arcs (arc_id, story_id, arc_number, outline, created_at)
                 VALUES (?, ?, ?, ?, ?)''', (arc_id, story_id, arc_number, outline, now))
    conn.commit()
    conn.close()
    return arc_id

def get_story_list():
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT story_id, outline, created_at FROM stories''')
    results = c.fetchall()
    conn.close()
    return [{"story_id": r[0], "outline": r[1], "created_at": datetime.fromisoformat(r[2])} for r in results]

def save_chapter(story_id, chapter_number, content):
    conn = get_db()
    c = conn.cursor()
    chapter_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    c.execute('''INSERT INTO chapters (chapter_id, story_id, chapter_number, content, created_at)
                 VALUES (?, ?, ?, ?, ?)''', (chapter_id, story_id, chapter_number, content, now))
    c.execute('''UPDATE stories SET last_updated = ? WHERE story_id = ?''', (now, story_id))
    conn.commit()
    conn.close()

def enhance_selected_text(text, enhancement_type):
    prompts = {
        "detail": "Hãy bổ sung thêm chi tiết cho đoạn văn sau (ngắn gọn):",
        "horror": "Hãy tăng cường yếu tố kinh dị cho đoạn văn sau (ngắn gọn):",
        "expand": "Hãy mở rộng đoạn văn sau (ngắn gọn):",
        "dialogue": "Hãy thêm đối thoại vào đoạn văn sau (ngắn gọn):"
    }
    
    messages = [
        {"role": "system", "content": "Bạn là một nhà văn chuyên viết truyện ma kinh dị. Hãy chỉnh sửa ngắn gọn và súc tích."},
        {"role": "user", "content": f"{prompts[enhancement_type]}\n\n{text}"}
    ]
    return call_api(messages, max_tokens=500)

def get_story_data(story_id):
    conn = get_db()
    c = conn.cursor()
    # Lấy thông tin truyện
    c.execute('''SELECT outline, created_at FROM stories WHERE story_id = ?''', (story_id,))
    story = c.fetchone()
    # Lấy các chương
    c.execute('''SELECT chapter_number, content, created_at FROM chapters
                 WHERE story_id = ? ORDER BY chapter_number''', (story_id,))
    chapters = c.fetchall()
    conn.close()
    
    if story:
        # Lấy tên truyện từ dòng đầu tiên của outline
        title = story[0].split('\n')[0]
        total_chapters = len(chapters)
        is_completed = total_chapters > 0 and total_chapters == int(story[0].split("Danh sách")[1].split("chương")[0].strip())
        
        return {
            "id": story_id,
            "title": title,
            "outline": story[0],
            "created_at": story[1],
            "total_chapters": total_chapters,
            "is_completed": is_completed,
            "chapters": [
                {
                    "chapter_number": chapter[0],
                    "content": chapter[1],
                    "created_at": chapter[2]
                }
                for chapter in chapters
            ]
        }
    return None

def publish_to_web(story_id):
    """Đẩy truyện lên website"""
    story_data = get_story_data(story_id)
    if not story_data:
        return False, "Không tìm thấy truyện"
    
    try:
        # Tạo thư mục static và templates nếu chưa có
        os.makedirs('static', exist_ok=True)
        os.makedirs('templates', exist_ok=True)
        
        # Lưu dữ liệu truyện vào file JSON
        stories_file = 'static/stories.json'
        stories = []
        if os.path.exists(stories_file):
            with open(stories_file, 'r', encoding='utf-8') as f:
                stories = json.load(f)
        
        # Cập nhật hoặc thêm mới truyện
        story_index = next((i for i, s in enumerate(stories) if s['id'] == story_id), -1)
        if story_index >= 0:
            stories[story_index] = story_data
        else:
            stories.append(story_data)
        
        # Lưu lại file JSON
        with open(stories_file, 'w', encoding='utf-8') as f:
            json.dump(stories, f, ensure_ascii=False, indent=2)
        
        return True, "Đã đẩy truyện lên web thành công"
    except Exception as e:
        return False, f"Lỗi khi đẩy truyện lên web: {str(e)}"

def export_to_word(story_id, file_path):
    story_data = get_story_data(story_id)
    if not story_data:
        return False
        
    doc = Document()
    # Thêm tiêu đề
    title = story_data['outline'].split('\n')[0]
    doc.add_heading(title, 0)
    
    # Thêm khung truyện
    doc.add_heading('Khung truyện', level=1)
    doc.add_paragraph(story_data['outline'])
    doc.add_paragraph('\n---\n')
    
    # Thêm các chương
    for chapter in story_data['chapters']:
        doc.add_heading(f'Chương {chapter["chapter_number"]}', level=1)
        doc.add_paragraph(chapter['content'])
        doc.add_paragraph('\n')
    
    doc.save(file_path)
    return True

def export_to_pdf(story_id, file_path):
    story_data = get_story_data(story_id)
    if not story_data:
        return False
        
    pdf = FPDF()
    pdf.add_page()
    
    # Cấu hình font cho tiếng Việt
    try:
        pdf.add_font('DejaVu', '', 'DejaVuSansCondensed.ttf', uni=True)
    except:
        # Nếu không có font DejaVu, dùng font mặc định
        pass
    
    pdf.set_font('Arial', '', 12)
    
    # Tiêu đề
    title = story_data['outline'].split('\n')[0]
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, title, ln=True, align='C')
    
    # Khung truyện
    pdf.set_font('Arial', '', 12)
    pdf.multi_cell(0, 10, story_data['outline'])
    pdf.ln()
    
    # Các chương
    for chapter in story_data['chapters']:
        pdf.add_page()
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, f'Chương {chapter["chapter_number"]}', ln=True)
        pdf.set_font('Arial', '', 12)
        pdf.multi_cell(0, 10, chapter['content'])
    
    try:
        pdf.output(file_path, 'F')
        return True
    except Exception as e:
        st.error(f"Lỗi khi xuất PDF: {str(e)}")
        return False

def get_chapter_versions(story_id, chapter_number):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT v.content, v.created_at
                 FROM chapter_versions v
                 JOIN chapters c ON v.chapter_id = c.chapter_id
                 WHERE c.story_id = ? AND c.chapter_number = ?
                 ORDER BY v.created_at DESC''', (story_id, chapter_number))
    versions = c.fetchall()
    conn.close()
    return [{"content": r[0], "created_at": datetime.fromisoformat(r[1])} for r in versions]

def save_chapter_version(story_id, chapter_number, content):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT chapter_id FROM chapters
                 WHERE story_id = ? AND chapter_number = ?''', (story_id, chapter_number))
    chapter = c.fetchone()
    if chapter:
        version_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        c.execute('''INSERT INTO chapter_versions (version_id, chapter_id, content, created_at)
                     VALUES (?, ?, ?, ?)''', (version_id, chapter[0], content, now))
        conn.commit()
    conn.close()
    return version_id if chapter else None

def delete_chapter(story_id, chapter_number):
    conn = get_db()
    c = conn.cursor()
    c.execute('''DELETE FROM chapters WHERE story_id = ? AND chapter_number = ?''',
              (story_id, chapter_number))
    conn.commit()
    conn.close()

def delete_story(story_id):
    conn = get_db()
    c = conn.cursor()
    # Xóa tất cả các phiên bản của các chương
    c.execute('''DELETE FROM chapter_versions 
                 WHERE chapter_id IN (
                     SELECT chapter_id FROM chapters WHERE story_id = ?
                 )''', (story_id,))
    # Xóa tất cả các chương
    c.execute('''DELETE FROM chapters WHERE story_id = ?''', (story_id,))
    # Xóa truyện
    c.execute('''DELETE FROM stories WHERE story_id = ?''', (story_id,))
    conn.commit()
    conn.close()

def get_story_chapters(story_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT chapter_number, content, created_at FROM chapters
                 WHERE story_id = ? ORDER BY chapter_number''', (story_id,))
    chapters = c.fetchall()
    conn.close()
    return [{"chapter_number": r[0], "content": r[1], "created_at": datetime.fromisoformat(r[2])} for r in chapters]

def export_chapter_to_word(chapter_data, file_path):
    doc = Document()
    doc.add_heading(f'Chương {chapter_data["chapter_number"]}', 0)
    doc.add_paragraph(chapter_data['content'])
    doc.save(file_path)
    return True

def export_all_chapters_to_word(story_id, file_path):
    story_data = get_story_data(story_id)
    if not story_data:
        return False
        
    doc = Document()
    # Thêm tiêu đề
    title = story_data['outline'].split('\n')[0]
    doc.add_heading(f"Tất cả các chương - {title}", 0)
    
    # Thêm các chương
    for chapter in story_data['chapters']:
        doc.add_heading(f'Chương {chapter["chapter_number"]}', level=1)
        doc.add_paragraph(chapter['content'])
        doc.add_page_break()
    
    doc.save(file_path)
    return True

def auto_generate_chapters(story_id, start_chapter, end_chapter, word_count):
    story_data = get_story_data(story_id)
    if not story_data:
        return False
    
    total_chapters = int(story_data['outline'].split("Danh sách")[1].split("chương")[0].strip())
    
    for chapter_number in range(start_chapter, end_chapter + 1):
        if chapter_number <= total_chapters:
            # Tạo nội dung chương
            chapter_content = generate_chapter(
                f"Viết chương {chapter_number}",
                story_data['outline'],
                chapter_number,
                total_chapters,
                word_count
            )
            # Lưu chương
            save_chapter(story_id, chapter_number, chapter_content)
    return True

def get_story_arcs(story_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT arc_number, outline, created_at FROM story_arcs
                 WHERE story_id = ? ORDER BY arc_number''', (story_id,))
    arcs = c.fetchall()
    conn.close()
    return [{"arc_number": r[0], "outline": r[1], "created_at": datetime.fromisoformat(r[2])} for r in arcs]

def generate_long_chapter(chapter_outline, story_outline, chapter_number, total_chapters, min_words=1000):
    """Tạo nội dung chương dài bằng cách chia thành nhiều phần và ghép lại"""
    
    # Chia thành 3 phần: mở đầu, thân truyện, kết thúc
    parts = []
    
    # Phần 1: Mở đầu (khoảng 20% nội dung)
    intro_messages = [
        {"role": "system", "content": f"""Bạn là một nhà văn chuyên viết truyện ma kinh dị.
        Hãy viết phần mở đầu của chương {chapter_number}/{total_chapters}.
        Dựa vào khung truyện sau:
        {story_outline}
        
        Yêu cầu:
        - Giới thiệu bối cảnh và tình huống
        - Tạo không khí rùng rợn
        - Độ dài khoảng {min_words//5} từ"""}
    ]
    intro = call_api(intro_messages, max_tokens=1000)
    parts.append(intro)
    
    # Phần 2: Thân truyện (khoảng 60% nội dung)
    main_messages = [
        {"role": "system", "content": f"""Tiếp tục viết phần thân truyện của chương {chapter_number}, sau phần mở đầu:
        {intro}
        
        Dựa vào outline:
        {chapter_outline}
        
        Yêu cầu:
        - Phát triển tình tiết chính
        - Tạo căng thẳng và kịch tính
        - Miêu tả chi tiết cảm xúc nhân vật
        - Độ dài khoảng {min_words*3//5} từ"""}
    ]
    main_content = call_api(main_messages, max_tokens=2000)
    parts.append(main_content)
    
    # Phần 3: Kết thúc (khoảng 20% nội dung)
    ending_messages = [
        {"role": "system", "content": f"""Viết phần kết thúc của chương {chapter_number}, sau phần:
        {main_content}
        
        Yêu cầu:
        - Tạo điểm nhấn hoặc twist
        - Kết nối với chương tiếp theo
        - Duy trì không khí rùng rợn
        - Độ dài khoảng {min_words//5} từ"""}
    ]
    ending = call_api(ending_messages, max_tokens=1000)
    parts.append(ending)
    
    # Ghép các phần lại
    full_chapter = "\n\n".join(parts)
    
    # Kiểm tra độ dài và tạo thêm nội dung nếu cần
    while len(full_chapter.split()) < min_words:
        expand_messages = [
            {"role": "system", "content": f"""Mở rộng đoạn văn sau, thêm chi tiết và miêu tả:
            {full_chapter}
            
            Yêu cầu:
            - Giữ nguyên cốt truyện
            - Thêm chi tiết miêu tả và đối thoại
            - Tăng độ dài thêm {min_words - len(full_chapter.split())} từ"""}
        ]
        expanded = call_api(expand_messages, max_tokens=1000)
        full_chapter = expanded
    
    return full_chapter

def main():
    global API_KEYS
    st.set_page_config(layout="wide")
    st.title("🏮 Công Cụ Tạo Truyện Ma Tự Động 👻")
    
    menu = st.sidebar.selectbox(
        "Chọn chức năng",
        ["Tạo Truyện Mới", "Tìm Kiếm Truyện", "Viết & Chỉnh Sửa", "Quản Lý Truyện"]
    )
    
    if menu == "Tạo Truyện Mới":
        st.header("Tạo Truyện Mới")
        
        col1, col2 = st.columns(2)
        with col1:
            num_chapters = st.number_input("Số chương:", min_value=1, max_value=2000, value=10)
            words_per_chapter = st.number_input("Số từ mỗi chương:", min_value=1000, max_value=10000, value=2000, step=500)
        
        # Thêm phần cấu hình API keys
        with st.expander("Cấu hình API"):
            api_keys_str = st.text_area(
                "Nhập các API key (mỗi key một dòng):",
                value="\n".join(API_KEYS),
                help="Thêm nhiều API key để tăng khả năng tạo nội dung dài"
            )
            if api_keys_str:
                API_KEYS[:] = [key.strip() for key in api_keys_str.split('\n') if key.strip()]
                st.success(f"Đã cập nhật {len(API_KEYS)} API key")

        prompt = st.text_area(
            "Nhập ý tưởng cho truyện của bạn:",
            height=150,
            help="Mô tả ý tưởng, bối cảnh, nhân vật, không khí truyện bạn muốn tạo"
        )
        
        if st.button("Tạo Khung Truyện"):
            if prompt:
                with st.spinner('Đang tạo khung truyện...'):
                    outline = generate_story_outline(prompt, num_chapters)
                    story_id = save_story_outline(outline, prompt)
                    st.markdown("### Khung Truyện:")
                    st.write(outline)
                    st.success(f"Đã lưu truyện với ID: {story_id}")
            else:
                st.warning("Vui lòng nhập ý tưởng cho truyện!")

    elif menu == "Tìm Kiếm Truyện":
        st.header("Tìm Kiếm Truyện")
        search_query = st.text_input("Nhập từ khóa tìm kiếm:")
        
        if search_query:
            stories = search_stories(search_query)
            if stories:
                st.success(f"Tìm thấy {len(stories)} kết quả")
                for story in stories:
                    with st.expander(f"Truyện tạo ngày {story['created_at'].strftime('%d/%m/%Y %H:%M')}"):
                        st.write(story['outline'])
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Chọn để chỉnh sửa", key=f"edit_{story['story_id']}"):
                                st.session_state['current_story'] = story['story_id']
                                st.session_state['current_outline'] = story['outline']
                        with col2:
                            if st.button("Viết lại", key=f"rewrite_{story['story_id']}"):
                                style = st.selectbox(
                                    "Chọn phong cách viết lại:",
                                    ["normal", "creative", "simple", "detailed"],
                                    format_func=lambda x: {
                                        "normal": "Bình thường",
                                        "creative": "Sáng tạo",
                                        "simple": "Đơn giản",
                                        "detailed": "Chi tiết"
                                    }[x]
                                )
                                rewritten = rewrite_story(story['outline'], style)
                                st.markdown("### Phiên bản viết lại:")
                                st.write(rewritten)
            else:
                st.info("Không tìm thấy truyện nào phù hợp")

    elif menu == "Viết & Chỉnh Sửa":
        st.header("Viết & Chỉnh Sửa Truyện")
        
        if 'current_story' in st.session_state:
            st.subheader("Khung Truyện")
            st.write(st.session_state['current_outline'])
            
            # Thêm phần quản lý arc
            st.subheader("Quản lý phần truyện")
            arcs = get_story_arcs(st.session_state['current_story'])
            
            col1, col2 = st.columns(2)
            with col1:
                next_arc = len(arcs) + 1
                num_chapters = st.number_input("Số chương cho phần mới:", min_value=1, max_value=50, value=10)
                if st.button("Tạo phần mới"):
                    with st.spinner(f'Đang tạo outline cho phần {next_arc}...'):
                        arc_outline = generate_arc_outline(st.session_state['current_outline'], next_arc, num_chapters)
                        arc_id = save_arc_outline(st.session_state['current_story'], next_arc, arc_outline)
                        st.success(f"Đã tạo phần {next_arc}")
                        st.rerun()
            
            with col2:
                if arcs:
                    st.write(f"Đã có {len(arcs)} phần")
                    for arc in arcs:
                        with st.expander(f"Phần {arc['arc_number']}"):
                            st.write(arc['outline'])
            
            st.markdown("---")
            
            # Thêm nút xuất file
            col_export1, col_export2, col_export3 = st.columns(3)
            with col_export1:
                if st.button("Xuất toàn bộ truyện (Word)"):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
                        if export_to_word(st.session_state['current_story'], tmp.name):
                            with open(tmp.name, 'rb') as f:
                                st.download_button(
                                    "Tải xuống truyện hoàn chỉnh",
                                    f,
                                    file_name="truyen_ma_full.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
            
            with col_export2:
                if st.button("Xuất tất cả các chương (Word)"):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
                        if export_all_chapters_to_word(st.session_state['current_story'], tmp.name):
                            with open(tmp.name, 'rb') as f:
                                st.download_button(
                                    "Tải xuống tất cả chương",
                                    f,
                                    file_name="tat_ca_chuong.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
            
            with col_export3:
                if st.button("Xuất file PDF"):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                        if export_to_pdf(st.session_state['current_story'], tmp.name):
                            with open(tmp.name, 'rb') as f:
                                st.download_button(
                                    "Tải xuống file PDF",
                                    f,
                                    file_name="truyen_ma.pdf",
                                    mime="application/pdf"
                                )
            
            # Thêm chức năng tự động tạo nhiều chương
            st.subheader("Tự động tạo chương")
            col_auto1, col_auto2, col_auto3 = st.columns(3)
            with col_auto1:
                start_chapter = st.number_input("Từ chương:", min_value=1, value=1)
            with col_auto2:
                end_chapter = st.number_input("Đến chương:", min_value=1, value=5)
            with col_auto3:
                auto_word_count = st.number_input("Số từ mỗi chương:", min_value=500, max_value=5000, value=1000, step=100)
            
            if st.button("Tự động tạo các chương"):
                total_chapters = int(st.session_state['current_outline'].split("Danh sách")[1].split("chương")[0].strip())
                if end_chapter > total_chapters:
                    st.error(f"Số chương tối đa là {total_chapters}")
                elif start_chapter > end_chapter:
                    st.error("Chương bắt đầu phải nhỏ hơn chương kết thúc")
                else:
                    with st.spinner(f'Đang tạo các chương từ {start_chapter} đến {end_chapter}...'):
                        if auto_generate_chapters(
                            st.session_state['current_story'],
                            start_chapter,
                            end_chapter,
                            auto_word_count
                        ):
                            st.success("Đã tạo xong các chương!")
                            st.rerun()
                        else:
                            st.error("Có lỗi xảy ra khi tạo chương")
            
            # Hiển thị danh sách các chương đã viết
            st.subheader("Các chương đã viết")
            chapters = get_story_chapters(st.session_state['current_story'])
            for chapter in chapters:
                with st.expander(f"Chương {chapter['chapter_number']} - {chapter['created_at'].strftime('%d/%m/%Y %H:%M')}"):
                    st.write(chapter['content'])
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        if st.button("Xóa", key=f"del_{chapter['chapter_number']}"):
                            delete_chapter(st.session_state['current_story'], chapter['chapter_number'])
                            st.success("Đã xóa chương!")
                            st.rerun()
                    with col2:
                        if st.button("Viết lại", key=f"rewrite_{chapter['chapter_number']}"):
                            new_content = rewrite_story(chapter['content'])
                            save_chapter_version(st.session_state['current_story'], chapter['chapter_number'], new_content)
                            st.success("Đã tạo phiên bản mới!")
                    with col3:
                        if st.button("Xem phiên bản", key=f"versions_{chapter['chapter_number']}"):
                            versions = get_chapter_versions(st.session_state['current_story'], chapter['chapter_number'])
                            for version in versions:
                                st.text(f"Phiên bản {version['created_at'].strftime('%d/%m/%Y %H:%M')}")
                                st.text_area("Nội dung:", version['content'], height=200, key=f"v_{version['version_id']}")
                    with col4:
                        if st.button("Chỉnh sửa", key=f"edit_{chapter['chapter_number']}"):
                            st.session_state['editing_chapter'] = chapter['chapter_number']
                            st.session_state['editing_content'] = chapter['content']
                    with col5:
                        if st.button("Xuất Word", key=f"export_{chapter['chapter_number']}"):
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
                                if export_chapter_to_word(chapter, tmp.name):
                                    with open(tmp.name, 'rb') as f:
                                        st.download_button(
                                            f"Tải Chương {chapter['chapter_number']}",
                                            f,
                                            file_name=f"chuong_{chapter['chapter_number']}.docx",
                                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                            key=f"download_{chapter['chapter_number']}"
                                        )
            
            # Hiển thị tổng quan về tiến độ
            st.markdown("---")
            st.subheader("Tiến độ truyện")
            total_chapters = int(st.session_state['current_outline'].split("Danh sách")[1].split("chương")[0].strip())
            progress = len(chapters) / total_chapters
            st.progress(progress)
            st.write(f"Đã viết: {len(chapters)}/{total_chapters} chương")
            
            st.markdown("---")
            
            # Khu vực viết và chỉnh sửa
            col1, col2 = st.columns([6, 4])
            
            with col1:
                st.subheader("Viết Chương Mới")
                next_chapter = len(chapters) + 1
                if next_chapter <= total_chapters:
                    chapter_number = st.number_input("Số chương:", min_value=1, max_value=total_chapters, value=next_chapter)
                    word_count = st.number_input("Số từ:", min_value=500, max_value=5000, value=1000, step=100)
                    
                    if st.button("Tạo nội dung chương"):
                        chapter_content = generate_chapter(
                            f"Viết chương {chapter_number}",
                            st.session_state['current_outline'],
                            chapter_number,
                            total_chapters,
                            word_count
                        )
                        st.session_state['current_chapter'] = chapter_content
                        st.write(chapter_content)
                    
                    chapter_content = st.text_area(
                        "Nội dung chương:",
                        value=st.session_state.get('current_chapter', ''),
                        height=400
                    )
                    
                    if st.button("Lưu chương"):
                        if 'editing_chapter' in st.session_state:
                            # Lưu phiên bản mới khi đang chỉnh sửa
                            save_chapter_version(st.session_state['current_story'], st.session_state['editing_chapter'], chapter_content)
                            del st.session_state['editing_chapter']
                        else:
                            # Lưu chương mới
                            save_chapter(st.session_state['current_story'], chapter_number, chapter_content)
                        st.success("Đã lưu chương thành công!")
                        st.rerun()
                else:
                    st.warning("Đã hoàn thành tất cả các chương!")

        else:
            st.info("Vui lòng chọn một truyện từ Tìm Kiếm Truyện để bắt đầu chỉnh sửa")

    elif menu == "Quản Lý Truyện":
        st.header("Quản Lý Truyện")
        stories = get_story_list()
        
        if not stories:
            st.info("Chưa có truyện nào được tạo")
        else:
            st.success(f"Có {len(stories)} truyện")
            
            # Tạo bảng hiển thị
            col_titles = st.columns([3, 2, 1, 1, 1, 1, 1])
            col_titles[0].markdown("### Tên truyện")
            col_titles[1].markdown("### Ngày tạo")
            col_titles[2].markdown("### Số chương")
            col_titles[3].markdown("### Xóa")
            col_titles[4].markdown("### Xuất Word")
            col_titles[5].markdown("### Xuất chương")
            col_titles[6].markdown("### Đẩy web")
            
            st.markdown("---")
            
            for story in stories:
                # Khởi tạo session state cho xóa truyện
                delete_key = f"delete_{story['story_id']}"
                if delete_key not in st.session_state:
                    st.session_state[delete_key] = False
                
                cols = st.columns([3, 2, 1, 1, 1, 1, 1])
                
                # Lấy thông tin chi tiết truyện
                story_data = get_story_data(story['story_id'])
                title = story_data['title']
                total_chapters = story_data['total_chapters']
                
                # Cột tên truyện
                with cols[0]:
                    st.markdown(f"**{title}**")
                    if st.button("Xem chi tiết", key=f"view_{story['story_id']}"):
                        st.markdown("#### Chi tiết truyện:")
                        st.write(story['outline'])
                
                # Cột ngày tạo
                with cols[1]:
                    st.write(story['created_at'].strftime('%d/%m/%Y %H:%M'))
                
                # Cột số chương
                with cols[2]:
                    st.write(f"{total_chapters} chương")
                
                # Cột xóa truyện
                with cols[3]:
                    # Hiển thị nút xóa và xác nhận
                    if not st.session_state[delete_key]:
                        if st.button("🗑️", key=f"del_btn_{story['story_id']}"):
                            st.session_state[delete_key] = True
                    else:
                        st.warning("Xác nhận xóa?")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("✔️ Có", key=f"confirm_{story['story_id']}"):
                                delete_story(story['story_id'])
                                st.success("Đã xóa truyện!")
                                st.rerun()
                        with col2:
                            if st.button("❌ Không", key=f"cancel_{story['story_id']}"):
                                st.session_state[delete_key] = False
                                st.rerun()
                
                # Cột xuất toàn bộ Word
                with cols[4]:
                    if st.button("📄", key=f"export_full_{story['story_id']}"):
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
                            if export_to_word(story['story_id'], tmp.name):
                                with open(tmp.name, 'rb') as f:
                                    st.download_button(
                                        "Tải xuống",
                                        f,
                                        file_name=f"{title}.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                        key=f"download_full_{story['story_id']}"
                                    )
                
                # Cột xuất từng chương
                with cols[5]:
                    chapters = get_story_chapters(story['story_id'])
                    if chapters:
                        if st.button("📑", key=f"export_chapters_{story['story_id']}"):
                            st.markdown("#### Tải xuống từng chương:")
                            for chapter in chapters:
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
                                    if export_chapter_to_word(chapter, tmp.name):
                                        with open(tmp.name, 'rb') as f:
                                            st.download_button(
                                                f"Chương {chapter['chapter_number']}",
                                                f,
                                                file_name=f"{title}_chuong_{chapter['chapter_number']}.docx",
                                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                                key=f"download_chapter_{story['story_id']}_{chapter['chapter_number']}"
                                            )
                
                # Cột đẩy lên web
                with cols[6]:
                    if st.button("🌐", key=f"publish_{story['story_id']}"):
                        success, message = publish_to_web(story['story_id'])
                        if success:
                            st.success(message)
                        else:
                            st.error(message)
                
                st.markdown("---")

if __name__ == "__main__":
    main() 