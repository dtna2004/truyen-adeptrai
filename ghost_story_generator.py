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
import time
import random
from PIL import Image
import io
from gtts import gTTS
from moviepy.editor import *
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
import numpy as np
import google.generativeai as genai
from io import BytesIO
from googletrans import Translator
import base64
import zhipuai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Endpoints and Keys
SD_API_ENDPOINT = os.getenv('SD_API_ENDPOINT', 'https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image')
SD_API_KEYS = os.getenv('SD_API_KEYS', '').split(',')
SD_API_KEYS = [key.strip() for key in SD_API_KEYS if key.strip()]
COGVIEW_API_KEY = os.getenv('COGVIEW_API_KEY')
zhipuai.api_key = COGVIEW_API_KEY
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
COLAB_API_URL = os.getenv('COLAB_API_URL', 'http://localhost:5000')

# FPT API Keys
FPT_API_KEYS = os.getenv('FPT_API_KEYS', 'rNz01K70Q2lG9s2tvF5oGUyQFa16EiwA').split(',')
FPT_API_KEYS = [key.strip() for key in FPT_API_KEYS if key.strip()]

def save_fpt_api_keys(api_keys):
    """Lưu danh sách API key FPT vào file .env"""
    try:
        # Đọc nội dung hiện tại của file .env
        env_content = ""
        if os.path.exists('.env'):
            with open('.env', 'r', encoding='utf-8') as f:
                env_content = f.read()
        
        # Tìm và thay thế hoặc thêm mới biến FPT_API_KEYS
        api_keys_str = ','.join(api_keys)
        if 'FPT_API_KEYS=' in env_content:
            # Thay thế giá trị cũ
            env_lines = env_content.splitlines()
            new_lines = []
            for line in env_lines:
                if line.startswith('FPT_API_KEYS='):
                    new_lines.append(f'FPT_API_KEYS={api_keys_str}')
                else:
                    new_lines.append(line)
            env_content = '\n'.join(new_lines)
        else:
            # Thêm biến mới
            env_content += f'\nFPT_API_KEYS={api_keys_str}'
        
        # Lưu lại file .env
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(env_content)
        
        return True
    except Exception as e:
        st.error(f"Lỗi khi lưu API keys: {str(e)}")
        return False

# Download NLTK data
nltk.download('punkt')

# Cấu hình API
API_KEYS = [
    "AIzaSyA6-W9fSgwDFSjf2i-gnirXwfaiah6M2zg",
    "AIzaSyC7lFa-0ZHvh09Hm4TtYfVc894UQXggLX0",
    "AIzaSyBWS4VBDtvkkbkvZyaawUbWAle4sXPS7YU",
    "AIzaSyAiAXsuJ9o1bCjaaRh2aUUYaTiZIFvU0Co",
    "AIzaSyDqESoT7B7CIkxfLBdC3DzbgjxbSVjq36o"
    # Thêm các API key khác vào đây
]
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

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

        try:
            api_key = get_next_api_key()
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
                continue

            if 'candidates' in response_json:
                return response_json['candidates'][0]['content']['parts'][0]['text']
                
        except Exception as e:
            st.error(f"Lỗi: {str(e)}")
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

def generate_story_outline(prompt, num_chapters=10, genre="horror", warnings=None, style=None, custom_genre_guide=None, custom_style_guide=None):
    # Tạo hướng dẫn dựa trên thể loại
    genre_guides = {
        "horror": """Bạn là một nhà văn chuyên viết truyện ma kinh dị. 
        Hãy tạo một khung truyện kinh dị, rùng rợn với những tình tiết giật gân và bầu không khí u ám.""",
        
        "romance": """Bạn là một nhà văn chuyên viết truyện tình cảm lãng mạn.
        Hãy tạo một khung truyện tình cảm sâu sắc, tập trung vào cảm xúc và mối quan hệ giữa các nhân vật.""",
        
        "cultivation": """Bạn là một nhà văn chuyên viết truyện tu tiên, võ hiệp.
        Hãy tạo một khung truyện tu tiên với hệ thống tu luyện rõ ràng, các cấp độ công pháp và thế giới võ lâm huyền ảo.""",
        
        "action": """Bạn là một nhà văn chuyên viết truyện hành động.
        Hãy tạo một khung truyện hành động gay cấn với những pha đánh đấm, rượt đuổi và đối đầu kịch tính.""",
        
        "fantasy": """Bạn là một nhà văn chuyên viết truyện giả tưởng.
        Hãy tạo một khung truyện với thế giới kỳ ảo, phép thuật và sinh vật huyền bí.""",

        "210": """Bạn là một nhà văn chuyên viết truyện 18+.
        Hãy tạo một khung truyện với nội dung 18+, không phù hợp với độc giả dưới 18 tuổi.""",
        
        "custom": custom_genre_guide  # Thêm hướng dẫn tùy chỉnh
    }
    
    # Tạo cảnh báo nội dung
    warning_notes = []
    if warnings:
        if "18+" in warnings:
            warning_notes.append("- Cảnh báo: Truyện có nội dung 18+, không phù hợp với độc giả dưới 18 tuổi")
        if "violence" in warnings:
            warning_notes.append("- Cảnh báo: Truyện có cảnh bạo lực")
        if "horror" in warnings:
            warning_notes.append("- Cảnh báo: Truyện có cảnh kinh dị, rùng rợn")
        if "sensitive" in warnings:
            warning_notes.append("- Cảnh báo: Truyện có nội dung nhạy cảm")
    
    # Tạo hướng dẫn về phong cách
    style_guides = {
        "dark": "Tạo bầu không khí u tối, nặng nề",
        "light": "Tạo bầu không khí nhẹ nhàng, tươi sáng",
        "comedy": "Thêm các yếu tố hài hước",
        "serious": "Giữ giọng văn nghiêm túc, sâu sắc",
        "poetic": "Sử dụng nhiều hình ảnh và ẩn dụ thơ mộng",
        "210": "Tạo bầu không khí lãng mạn, dâm dục và quyến rũ",
        "custom": custom_style_guide  # Thêm phong cách tùy chỉnh
    }
    
    # Lấy hướng dẫn phong cách
    style_note = style_guides.get(style, "")
    if style == "custom" and custom_style_guide:
        style_note = custom_style_guide
    
    # Lấy hướng dẫn thể loại
    genre_guide = genre_guides.get(genre, "")
    if genre == "custom" and custom_genre_guide:
        genre_guide = custom_genre_guide
    
    messages = [
        {"role": "system", "content": f"""{genre_guide}
        
        {style_note}
        
        Hãy tạo một khung truyện chi tiết bằng tiếng Việt, bao gồm:
        1. Tên truyện
        2. Thể loại chính: {genre if genre != "custom" else "Tùy chỉnh"}
        3. Thể loại phụ (nếu có)
        4. Độ tuổi khuyến nghị và cảnh báo nội dung:
        {chr(10).join(warning_notes) if warning_notes else "- Không có cảnh báo đặc biệt"}
        
        5. Giới thiệu ngắn (1-2 đoạn)
        
        6. Nhân vật chính:
           - Tên và vai trò
           - Đặc điểm ngoại hình và tính cách
           - Động lực và mục tiêu
           
        7. Nhân vật phụ:
           - Danh sách nhân vật quan trọng
           - Mối quan hệ với nhân vật chính
           
        8. Bối cảnh:
           - Thời gian và không gian
           - Không khí và màu sắc truyện
           - Quy tắc/Hệ thống thế giới (nếu có)
           
        9. Cốt truyện chính:
           - Điểm khởi đầu
           - Các tình tiết chính
           - Điểm cao trào
           - Kết thúc
           
        10. Số phần dự kiến và nội dung chính của mỗi phần
        
        11. Danh sách {num_chapters} chương cho phần 1:
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

def generate_chapter(chapter_outline, story_outline, chapter_number, total_chapters, word_count, warnings=None):
    """Tạo nội dung chương với nhiều phong cách và chi tiết hơn"""
    
    # Lấy tóm tắt các chương trước
    previous_chapters_summary = ""
    if chapter_number > 1:
        conn = get_db()
        c = conn.cursor()
        c.execute('''SELECT chapter_number, content FROM chapters 
                     WHERE story_id = (
                         SELECT story_id FROM chapters 
                         WHERE chapter_number = ? 
                         LIMIT 1
                     ) AND chapter_number < ?
                     ORDER BY chapter_number''', (chapter_number, chapter_number))
        prev_chapters = c.fetchall()
        conn.close()
        
        if prev_chapters:
            previous_chapters_summary = "\n".join([
                f"Chương {ch[0]}: {ch[1][:200]}..." for ch in prev_chapters
            ])
        else:
            previous_chapters_summary = "Chưa có chương trước."
    
    # Xác định phong cách và nội dung dựa trên cảnh báo
    content_style = ""
    if warnings:
        if "18+" in warnings:
            content_style += """
            - Thêm các chi tiết về cảnh nóng, quan hệ tình dục một cách tinh tế
            - Miêu tả cảm xúc và ham muốn của nhân vật
            - Sử dụng ngôn từ gợi cảm nhưng không thô tục
            - Tạo không khí lãng mạn và quyến rũ
            """
        if "violence" in warnings:
            content_style += """
            - Thêm các cảnh hành động và bạo lực
            - Miêu tả chi tiết các cuộc đấu tranh
            - Thể hiện sự tàn nhẫn và đau đớn
            """
        if "horror" in warnings:
            content_style += """
            - Tạo không khí kinh dị và rùng rợn
            - Thêm các yếu tố siêu nhiên đáng sợ
            - Miêu tả nỗi sợ hãi và ám ảnh
            """
    
    # Tạo danh sách các kiểu mở đầu đa dạng
    opening_styles = [
        "Bắt đầu với một cảnh hành động gay cấn",
        "Mở đầu bằng đối thoại ấn tượng",
        "Khởi đầu với một cảnh tượng bí ẩn",
        "Bắt đầu từ một khoảnh khắc tình cảm",
        "Mở đầu với một cảnh tượng gợi cảm",
        "Khởi đầu từ một giấc mơ hoặc ảo giác",
        "Bắt đầu với một sự kiện bất ngờ",
        "Mở đầu bằng một hồi tưởng",
        "Bắt đầu với một câu hỏi đầy triết lý",
        "Mở đầu theo phong cách báo chí hoặc tài liệu"
    ]
    
    # Chọn ngẫu nhiên kiểu mở đầu
    opening_style = random.choice(opening_styles)
    
    messages = [
        {"role": "system", "content": f"""Bạn là một nhà văn chuyên nghiệp.
        Hãy viết chương {chapter_number}/{total_chapters} với độ dài khoảng {word_count} từ.
        
        Tóm tắt toàn bộ truyện:
        {story_outline}
        
        Tóm tắt các chương trước:
        {previous_chapters_summary}
        
        Outline chương hiện tại:
        {chapter_outline}
        
        Phong cách và yêu cầu đặc biệt:
        {content_style}
        
        Yêu cầu chung:
        - {opening_style}
        - Đảm bảo tính liên tục và nhất quán với các chương trước
        - Phát triển tình tiết tự nhiên, không gượng ép
        - Xây dựng tâm lý và cảm xúc nhân vật sâu sắc
        - Tạo ra những tình huống bất ngờ nhưng hợp lý
        - Kết hợp hài hòa giữa miêu tả, đối thoại và hành động
        - Sử dụng ngôn ngữ phù hợp với thể loại và đối tượng độc giả
        - Tạo điểm nhấn và cao trào cho chương
        - Duy trì sự phát triển của các nhân vật và mạch truyện chính
        """},
        {"role": "user", "content": f"Viết chương {chapter_number} dựa trên outline đã cho và đảm bảo tính liên tục với các chương trước"}
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

def text_to_speech(text, voice="banmai", speed="", api_key=None):
    """Chuyển đổi text thành speech sử dụng FPT API với nhiều API key"""
    global FPT_API_KEYS
    
    if not FPT_API_KEYS:
        FPT_API_KEYS = ["rNz01K70Q2lG9s2tvF5oGUyQFa16EiwA"]  # API key mặc định
    
    # Nếu có api_key được chỉ định, thử với key đó trước
    if api_key:
        keys_to_try = [api_key] + [k for k in FPT_API_KEYS if k != api_key]
    else:
        keys_to_try = FPT_API_KEYS
    
    url = 'https://api.fpt.ai/hmi/tts/v5'
    
    # Thử với từng API key cho đến khi thành công
    for current_key in keys_to_try:
        try:
            headers = {
                'api-key': current_key,
                'speed': speed,
                'voice': voice
            }
            
            response = requests.post(url, data=text.encode('utf-8'), headers=headers)
            if response.status_code == 200:
                response_data = response.json()
                if 'async' in response_data:
                    audio_url = response_data['async']
                    
                    # Tạo thư mục audio nếu chưa có
                    os.makedirs('static/audio', exist_ok=True)
                    audio_filename = f"audio_{uuid.uuid4()}.mp3"
                    audio_path = os.path.join('static/audio', audio_filename)
                    
                    # Thử tải file audio với nhiều lần thử
                    max_retries = 10  # Tăng số lần thử
                    retry_delay = 3   # Giảm thời gian đợi giữa các lần thử
                    
                    for attempt in range(max_retries):
                        try:
                            time.sleep(retry_delay)
                            
                            # Kiểm tra trạng thái audio trước khi tải
                            status_response = requests.get(audio_url, timeout=10)
                            
                            if status_response.status_code == 200:
                                # Tải file audio
                                audio_response = requests.get(audio_url, timeout=30)
                                
                                if len(audio_response.content) > 1000:  # Kiểm tra kích thước tối thiểu
                                    with open(audio_path, 'wb') as f:
                                        f.write(audio_response.content)
                                    
                                    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                                        return True, {'url': audio_url, 'local_path': audio_path}
                                    
                            elif status_response.status_code == 404:
                                if attempt < max_retries - 1:
                                    continue
                                else:
                                    break  # Thử API key tiếp theo
                                    
                        except requests.Timeout:
                            if attempt < max_retries - 1:
                                continue
                            else:
                                break  # Thử API key tiếp theo
                                
                        except Exception as e:
                            if attempt < max_retries - 1:
                                continue
                            else:
                                break  # Thử API key tiếp theo
                    
                    # Nếu đã thử hết số lần với API key hiện tại, tiếp tục với API key khác
                    continue
                    
            elif response.status_code == 401:  # API key không hợp lệ
                continue  # Thử API key tiếp theo
                
        except Exception as e:
            continue  # Thử API key tiếp theo
    
    return False, "Không thể tạo audio sau khi thử tất cả API key. Vui lòng kiểm tra lại API key hoặc thử lại sau."

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
        title = story[0].split('\n')[0] if story[0] else "Không có tiêu đề"
        
        # Đếm tổng số chương từ outline một cách an toàn
        try:
            # Tìm phần "Danh sách X chương"
            if "Danh sách" in story[0]:
                parts = story[0].split("Danh sách")
                if len(parts) > 1:
                    num_str = parts[1].split("chương")[0].strip()
                    total_chapters = int(num_str) if num_str.isdigit() else 10
                else:
                    total_chapters = 10
            else:
                # Đếm số lần xuất hiện của "Chương" trong outline
                chapter_count = story[0].lower().count("chương")
                total_chapters = chapter_count if chapter_count > 0 else 10
        except:
            total_chapters = 10  # Giá trị mặc định nếu không thể xác định
        
        # Thêm audio_url vào thông tin chương
        chapter_data = []
        for chapter in chapters:
            chapter_info = {
                "chapter_number": chapter[0],
                "content": chapter[1],
                "created_at": chapter[2],
                "audio_url": None  # Mặc định không có audio
            }
            chapter_data.append(chapter_info)
        
        return {
            "id": story_id,
            "title": title,
            "outline": story[0],
            "created_at": story[1],
            "total_chapters": total_chapters,
            "is_completed": len(chapters) >= total_chapters,
            "chapters": chapter_data
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
    
    total_chapters = get_total_chapters_from_outline(story_data['outline'])
    
    # Lấy cảnh báo nội dung từ outline
    warnings = []
    if "18+" in story_data['outline'].lower():
        warnings.append("18+")
    if "bạo lực" in story_data['outline'].lower():
        warnings.append("violence")
    if "kinh dị" in story_data['outline'].lower():
        warnings.append("horror")
    
    for chapter_number in range(start_chapter, end_chapter + 1):
        if chapter_number <= total_chapters:
            # Tạo nội dung chương với cảnh báo
            chapter_content = generate_chapter(
                f"Viết chương {chapter_number}",
                story_data['outline'],
                chapter_number,
                total_chapters,
                word_count,
                warnings=warnings
            )
            # Lưu chương
            save_chapter(story_id, chapter_number, chapter_content)
    return True

def get_total_chapters_from_outline(outline):
    """Lấy tổng số chương từ outline với xử lý lỗi"""
    try:
        # Tìm phần "Danh sách X chương"
        if not outline or "Danh sách" not in outline:
            return 10  # Giá trị mặc định nếu không tìm thấy
        
        # Tìm số chương bằng regex
        import re
        
        # Thử tìm theo mẫu "Danh sách X chương"
        matches = re.findall(r'Danh sách\s+(\d+)\s+chương', outline)
        if matches:
            return int(matches[0])
            
        # Thử tìm theo mẫu "X chương"
        matches = re.findall(r'(\d+)\s+chương', outline)
        if matches:
            return int(matches[0])
            
        # Thử tìm theo mẫu "Chương X:"
        chapter_numbers = re.findall(r'Chương\s+(\d+):', outline)
        if chapter_numbers:
            return max(map(int, chapter_numbers))
        
        # Đếm số lần xuất hiện của từ "Chương"
        chapter_count = len(re.findall(r'Chương\s+\d+', outline, re.IGNORECASE))
        if chapter_count > 0:
            return chapter_count
        
        return 10  # Giá trị mặc định nếu không tìm được số
    except Exception as e:
        st.error(f"Lỗi khi đọc số chương: {str(e)}")
        return 10  # Giá trị mặc định nếu có lỗi

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
    st.title("Trình Tạo Truyện Ma")
    
    # Menu chính
    menu = st.sidebar.selectbox(
        "Chọn chức năng:",
        ["Tạo Truyện Mới", "Danh Sách Truyện", "Tạo Audio", "Tạo Video", "Cài Đặt"]
    )
    
    if menu == "Tạo Truyện Mới":
        st.header("Tạo Truyện Mới")
        
        # Tạo layout 2 cột cho các tùy chọn
        col1, col2 = st.columns(2)
        
        with col1:
            # Chọn thể loại chính
            genre_options = {
                "horror": "Truyện Ma - Kinh Dị",
                "romance": "Tình Cảm - Lãng Mạn",
                "cultivation": "Tu Tiên - Võ Hiệp",
                "action": "Hành Động - Phiêu Lưu",
                "fantasy": "Giả Tưởng - Kỳ Ảo",
                "210": "18+ - 210 :)))",
                "custom": "Thể Loại Tùy Chỉnh"
            }
            genre = st.selectbox(
                "Chọn thể loại:",
                options=list(genre_options.keys()),
                format_func=lambda x: genre_options[x]
            )
            
            # Nếu chọn thể loại tùy chỉnh
            custom_genre_guide = None
            if genre == "custom":
                custom_genre_name = st.text_input("Tên thể loại mới:")
                custom_genre_guide = st.text_area(
                    "Mô tả hướng dẫn cho thể loại:",
                    help="Mô tả chi tiết về đặc điểm, yêu cầu và phong cách của thể loại này"
                )
            
            # Chọn phong cách viết
            style_options = {
                "dark": "U tối, nặng nề",
                "light": "Nhẹ nhàng, tươi sáng",
                "comedy": "Hài hước",
                "serious": "Nghiêm túc",
                "poetic": "Thơ mộng",
                "210": "18+ - 210 :)))",
                "custom": "Phong Cách Tùy Chỉnh"
            }
            style = st.selectbox(
                "Chọn phong cách:",
                options=list(style_options.keys()),
                format_func=lambda x: style_options[x]
            )
            
            # Nếu chọn phong cách tùy chỉnh
            custom_style_guide = None
            if style == "custom":
                custom_style_name = st.text_input("Tên phong cách mới:")
                custom_style_guide = st.text_area(
                    label="Mô tả hướng dẫn cho phong cách:",
                    help="Mô tả chi tiết về cách viết, giọng văn và không khí của phong cách này"
                )
        
        with col2:
            # Chọn các cảnh báo nội dung
            warnings = st.multiselect(
                "Cảnh báo nội dung:",
                ["18+", "violence", "horror", "sensitive"],
                format_func=lambda x: {
                    "18+": "Nội dung 18+",
                    "violence": "Bạo lực",
                    "horror": "Kinh dị",
                    "sensitive": "Nội dung nhạy cảm"
                }[x]
            )
            
            # Cấu hình độ dài truyện
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

        # Nhập ý tưởng truyện
        prompt = st.text_area(
            "Nhập ý tưởng cho truyện của bạn:",
            height=150,
            help="Mô tả ý tưởng, bối cảnh, nhân vật, không khí truyện bạn muốn tạo"
        )
        
        if st.button("Tạo Khung Truyện"):
            if prompt:
                with st.spinner('Đang tạo khung truyện...'):
                    outline = generate_story_outline(
                        prompt,
                        num_chapters=num_chapters,
                        genre=genre,
                        warnings=warnings,
                        style=style,
                        custom_genre_guide=custom_genre_guide,
                        custom_style_guide=custom_style_guide
                    )
                    story_id = save_story_outline(outline, prompt)
                    st.markdown("### Khung Truyện:")
                    st.write(outline)
                    st.success(f"Đã lưu truyện với ID: {story_id}")
            else:
                st.warning("Vui lòng nhập ý tưởng cho truyện!")

    elif menu == "Danh Sách Truyện":
        st.header("Danh Sách Truyện")
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
                                st.rerun()
                        with col2:
                            # Xử lý viết lại truyện
                            rewrite_button = st.button("Viết lại", key=f"rewrite_{story['story_id']}")
                            if rewrite_button:
                                style = st.selectbox(
                                    "Chọn phong cách viết lại:",
                                    ["normal", "creative", "simple", "detailed"],
                                    format_func=lambda x: {
                                        "normal": "Bình thường",
                                        "creative": "Sáng tạo", 
                                        "simple": "Đơn giản",
                                        "detailed": "Chi tiết"
                                    }[x],
                                    key=f"style_{story['story_id']}"
                                )
                                
                                confirm_button = st.button("Xác nhận viết lại", key=f"confirm_rewrite_{story['story_id']}")
                                if confirm_button:
                                    with st.spinner('Đang viết lại truyện...'):
                                        rewritten = rewrite_story(story['outline'], style)
                                        st.markdown("### Phiên bản viết lại:")
                                        st.write(rewritten)
            else:
                st.info("Không tìm thấy truyện nào phù hợp")

    elif menu == "Tạo Audio":
        st.header("Tạo Audio Từ Truyện")
        
        # Phần cấu hình API FPT
        st.subheader("Cấu hình API FPT")
        api_keys_str = st.text_area(
            "Nhập các API key FPT (mỗi key một dòng):",
            value="rNz01K70Q2lG9s2tvF5oGUyQFa16EiwA",  # API key mặc định
            help="Thêm nhiều API key để tăng khả năng chuyển đổi"
        )
        fpt_api_keys = [key.strip() for key in api_keys_str.split('\n') if key.strip()]
        
        # Chọn truyện để tạo audio
        stories = get_story_list()
        if not stories:
            st.info("Chưa có truyện nào được tạo")
        else:
            selected_story = st.selectbox(
                "Chọn truyện để tạo audio:",
                options=[story['story_id'] for story in stories],
                format_func=lambda x: next(s['outline'].split('\n')[0] for s in stories if s['story_id'] == x)
            )
            
            if selected_story:
                story_data = get_story_data(selected_story)
                chapters = get_story_chapters(selected_story)
                
                # Cấu hình giọng đọc
                col1, col2 = st.columns(2)
                with col1:
                    voice = st.selectbox(
                        "Chọn giọng đọc:",
                        ["banmai", "thuminh", "leminh", "myan", "lannhi", "linhsan"]
                    )
                with col2:
                    speed = st.slider(
                        "Tốc độ đọc:",
                        min_value=-3,
                        max_value=3,
                        value=0
                    )
                
                # Hiển thị danh sách chương và nút tạo audio
                st.subheader(f"Danh sách chương - {story_data['title']}")
                
                for chapter in chapters:
                    with st.expander(f"Chương {chapter['chapter_number']}"):
                        st.write(chapter['content'][:200] + "...")  # Hiển thị preview nội dung
                        
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            # Kiểm tra xem đã có audio chưa
                            if 'audio_url' in chapter and chapter['audio_url']:
                                st.markdown(f"""
                                <audio controls>
                                    <source src="{chapter['audio_url']}" type="audio/mp3">
                                    Trình duyệt của bạn không hỗ trợ audio.
                                </audio>
                                """, unsafe_allow_html=True)
                            else:
                                st.info("Chưa có audio")
                        
                        with col2:
                            if st.button("Tạo Audio", key=f"create_audio_{chapter['chapter_number']}"):
                                with st.spinner('Đang tạo audio...'):
                                    # Thử với từng API key cho đến khi thành công
                                    for api_key in fpt_api_keys:
                                        success, result = text_to_speech(
                                            chapter['content'],
                                            voice=voice,
                                            speed=str(speed),
                                            api_key=api_key
                                        )
                                        if success:
                                            st.success("Đã tạo audio thành công!")
                                            # Hiển thị audio player
                                            st.markdown(f"""
                                            <audio controls>
                                                <source src="{result['url']}" type="audio/mp3">
                                                Trình duyệt của bạn không hỗ trợ audio.
                                            </audio>
                                            """, unsafe_allow_html=True)
                                            
                                            # Thêm nút tải về
                                            with open(result['local_path'], 'rb') as f:
                                                st.download_button(
                                                    label="Tải audio về máy",
                                                    data=f,
                                                    file_name=f"chuong_{chapter['chapter_number']}_audio.mp3",
                                                    mime="audio/mp3"
                                                )
                                            
                                            # Lưu URL audio vào database
                                            save_audio_url(selected_story, chapter['chapter_number'], result)
                                            break
                                        else:
                                            st.error(f"Lỗi với API key {api_key[:10]}...: {result}")
                                            continue
    
    elif menu == "Tạo Video":
        st.header("Tạo Video Từ Truyện")
        
        # Chọn truyện để tạo video
        stories = get_story_list()
        if not stories:
            st.info("Chưa có truyện nào được tạo")
        else:
            # Tạo dictionary ánh xạ story_id với tên truyện
            story_titles = {}
            for story in stories:
                title = story['outline'].split('\n')[0] if story['outline'] else "Không có tiêu đề"
                story_titles[story['story_id']] = title
            
            selected_story = st.selectbox(
                "Chọn truyện để tạo video:",
                options=list(story_titles.keys()),
                format_func=lambda x: story_titles[x]
            )
            
            if selected_story:
                story_data = get_story_data(selected_story)
                chapters = get_story_chapters(selected_story)
                
                # Hiển thị thông tin truyện
                st.subheader(f"Thông tin truyện: {story_data['title']}")
                st.write(f"Tổng số chương: {story_data['total_chapters']}")
                st.write(f"Số chương đã viết: {len(chapters)}")
                
                # Cấu hình tạo video
                st.subheader("Cấu hình tạo video")
                
                col1, col2 = st.columns(2)
                with col1:
                    # Chọn phong cách hình ảnh
                    style = st.selectbox(
                        "Chọn phong cách hình ảnh",
                        ["realistic", "anime", "digital art", "oil painting", "watercolor", 
                         "pencil sketch", "3D render", "pixel art", "comic book"]
                    )
                
                with col2:
                    # Chọn model tạo hình ảnh
                    model = st.selectbox(
                        "Chọn model tạo hình ảnh",
                        ["stable-diffusion", "cogview", "gemini"],
                        help="""
                        - Stable Diffusion: Cho kết quả tốt và ổn định
                        - CogView: Phù hợp với nội dung tiếng Trung
                        - Gemini: API mới từ Google (đang thử nghiệm)
                        """
                    )
                
                # Cấu hình giọng đọc
                st.subheader("Cấu hình giọng đọc")
                col3, col4 = st.columns(2)
                with col3:
                    voice = st.selectbox(
                        "Chọn giọng đọc:",
                        ["banmai", "thuminh", "leminh", "myan", "lannhi", "linhsan"]
                    )
                with col4:
                    speed = st.slider(
                        "Tốc độ đọc:",
                        min_value=-3,
                        max_value=3,
                        value=0
                    )
                
                # Chọn chương để tạo video
                st.subheader("Chọn chương để tạo video")
                selected_chapters = st.multiselect(
                    "Chọn các chương muốn tạo video:",
                    options=[f"Chương {chapter['chapter_number']}" for chapter in chapters],
                    default=[f"Chương {chapters[0]['chapter_number']}"] if chapters else None
                )
                
                if selected_chapters and st.button("Tạo Video"):
                    with st.spinner('Đang tạo video...'):
                        try:
                            # Khởi tạo StoryContext để theo dõi nhân vật và cảnh
                            story_context = StoryContext()
                            
                            for chapter_name in selected_chapters:
                                chapter_num = int(chapter_name.split()[1])
                                chapter = next(c for c in chapters if c['chapter_number'] == chapter_num)
                                
                                st.write(f"Đang xử lý {chapter_name}...")
                                
                                # Chia chương thành các cảnh
                                scenes = split_text_into_scenes(chapter['content'])
                                
                                # Tạo hình ảnh và audio cho từng cảnh
                                images = []
                                audio_files = []
                                
                                for i, scene in enumerate(scenes):
                                    st.write(f"Đang xử lý cảnh {i+1}/{len(scenes)}...")
                                    
                                    # Tạo prompt cho hình ảnh
                                    prompt = generate_consistent_prompt(scene, story_context, style, model)
                                    
                                    # Tạo hình ảnh
                                    image = generate_image(prompt, style, model)
                                    images.append(image)
                                    
                                    # Tạo audio
                                    success, result = text_to_speech(scene, voice, str(speed))
                                    if success:
                                        audio_files.append(result['local_path'])
                                    else:
                                        raise Exception(f"Lỗi khi tạo audio: {result}")
                                
                                # Tạo video cho chương
                                output_path = f"chapter_{chapter_num}_video.mp4"
                                create_video(scenes, images, audio_files, output_path)
                                
                                # Hiển thị video
                                st.success(f"Đã tạo xong video cho {chapter_name}!")
                                st.video(output_path)
                                
                                # Tạo nút tải xuống
                                with open(output_path, 'rb') as f:
                                    st.download_button(
                                        label=f"Tải video {chapter_name}",
                                        data=f,
                                        file_name=f"chapter_{chapter_num}_video.mp4",
                                        mime="video/mp4"
                                    )
                                
                                # Dọn dẹp file tạm
                                for audio_file in audio_files:
                                    if os.path.exists(audio_file):
                                        os.unlink(audio_file)
                                if os.path.exists(output_path):
                                    os.unlink(output_path)
                                
                        except Exception as e:
                            st.error(f"Lỗi khi tạo video: {str(e)}")
                            st.error("Chi tiết lỗi:")
                            st.exception(e)

    elif menu == "Cài Đặt":
        st.header("Cài Đặt API")
        
        # Quản lý API key FPT
        st.subheader("FPT Text-to-Speech API")
        
        # Hiển thị các API key hiện tại
        st.write("API key hiện tại:")
        for i, key in enumerate(FPT_API_KEYS):
            masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else key
            st.code(f"{i+1}. {masked_key}")
        
        # Thêm API key mới
        new_api_key = st.text_input("Nhập API key mới:", key="new_fpt_api_key")
        if st.button("Thêm API Key"):
            if new_api_key:
                if new_api_key not in FPT_API_KEYS:
                    FPT_API_KEYS.append(new_api_key)
                    if save_fpt_api_keys(FPT_API_KEYS):  # Lưu vào file .env
                        st.success("Đã thêm và lưu API key mới!")
                    else:
                        st.error("Thêm API key thành công nhưng không lưu được vào file .env")
                else:
                    st.warning("API key này đã tồn tại!")
            else:
                st.warning("Vui lòng nhập API key!")
        
        # Xóa API key
        if len(FPT_API_KEYS) > 0:
            st.subheader("Xóa API key")
            key_to_remove = st.selectbox(
                "Chọn API key cần xóa:",
                range(len(FPT_API_KEYS)),
                format_func=lambda x: f"API key {x+1}: {FPT_API_KEYS[x][:8]}...{FPT_API_KEYS[x][-4:]}"
            )
            if st.button("Xóa API Key"):
                if len(FPT_API_KEYS) > 1:  # Đảm bảo luôn còn ít nhất 1 API key
                    removed_key = FPT_API_KEYS.pop(key_to_remove)
                    if save_fpt_api_keys(FPT_API_KEYS):  # Lưu vào file .env
                        st.success(f"Đã xóa API key: {removed_key[:8]}...{removed_key[-4:]}")
                    else:
                        st.error("Xóa API key thành công nhưng không lưu được vào file .env")
                else:
                    st.error("Không thể xóa API key cuối cùng!")
        
        # Kiểm tra API key
        st.subheader("Kiểm tra API key")
        key_to_test = st.selectbox(
            "Chọn API key cần kiểm tra:",
            range(len(FPT_API_KEYS)),
            format_func=lambda x: f"API key {x+1}: {FPT_API_KEYS[x][:8]}...{FPT_API_KEYS[x][-4:]}"
        )
        if st.button("Kiểm tra"):
            test_text = "Xin chào, đây là bài kiểm tra API."
            success, result = text_to_speech(test_text, api_key=FPT_API_KEYS[key_to_test])
            if success:
                st.success("API key hoạt động tốt!")
                st.audio(result['local_path'])
            else:
                st.error(f"API key không hoạt động: {result}")

def save_audio_url(story_id, chapter_number, audio_data):
    """Lưu URL audio và đường dẫn local vào database"""
    conn = get_db()
    c = conn.cursor()
    
    # Thêm các cột audio nếu chưa có
    try:
        c.execute('ALTER TABLE chapters ADD COLUMN audio_url TEXT')
        c.execute('ALTER TABLE chapters ADD COLUMN audio_local_path TEXT')
    except sqlite3.OperationalError:
        pass  # Cột đã tồn tại
    
    # Cập nhật URL audio và đường dẫn local
    c.execute('''UPDATE chapters 
                 SET audio_url = ?, audio_local_path = ?
                 WHERE story_id = ? AND chapter_number = ?''',
              (audio_data['url'], audio_data['local_path'], story_id, chapter_number))
    conn.commit()
    conn.close()

class StoryContext:
    def __init__(self):
        self.characters = {}  # Lưu trữ thông tin nhân vật
        self.locations = {}   # Lưu trữ thông tin địa điểm
        self.current_scene = None  # Thông tin cảnh hiện tại
        self.style_prompt = ""  # Prompt về phong cách nhất quán
        self.last_scene_description = ""  # Mô tả cảnh trước đó
        self.character_first_descriptions = {}  # Lưu mô tả đầu tiên của nhân vật
        self.scene_history = []  # Lịch sử các cảnh
        
    def extract_entities(self, text):
        """Trích xuất nhân vật và địa điểm từ văn bản"""
        words = word_tokenize(text)
        
        # Tìm các cụm từ viết hoa có thể là tên riêng
        i = 0
        while i < len(words):
            word = words[i]
            if word[0].isupper() and (i > 0 or len(word) > 1):
                # Kết hợp các từ viết hoa liên tiếp
                name_parts = [word]
                j = i + 1
                while j < len(words) and words[j][0].isupper():
                    name_parts.append(words[j])
                    j += 1
                
                name = " ".join(name_parts)
                
                # Tìm mô tả xung quanh nhân vật
                context_start = max(0, i - 5)
                context_end = min(len(words), j + 5)
                context = " ".join(words[context_start:context_end])
                
                if name not in self.characters:
                    # Lưu thông tin nhân vật lần đầu xuất hiện
                    self.characters[name] = {
                        "first_appearance": text,
                        "first_context": context,
                        "description": self._extract_character_description(context),
                        "count": 1,
                        "scenes": [len(self.scene_history)]
                    }
                    self.character_first_descriptions[name] = self._extract_character_description(context)
                else:
                    self.characters[name]["count"] += 1
                    self.characters[name]["scenes"].append(len(self.scene_history))
                
                i = j
            else:
                i += 1
    
    def _extract_character_description(self, context):
        """Trích xuất mô tả nhân vật từ context"""
        # Tìm các từ mô tả xung quanh nhân vật
        description_keywords = ["là", "có", "mặc", "tuổi", "cao", "trông", "như", "giống"]
        description = ""
        
        for keyword in description_keywords:
            if keyword in context.lower():
                # Lấy phần văn bản sau keyword
                parts = context.lower().split(keyword)
                if len(parts) > 1:
                    # Lấy tối đa 10 từ sau keyword
                    desc = " ".join(parts[1].split()[:10])
                    if desc:
                        description += f"{keyword} {desc}. "
        
        return description.strip()
    
    def update_scene(self, text):
        """Cập nhật thông tin cảnh hiện tại"""
        self.last_scene_description = self.current_scene or ""
        self.current_scene = text
        self.scene_history.append(text)
        self.extract_entities(text)
    
    def get_character_descriptions(self):
        """Tạo mô tả về nhân vật cho prompt"""
        descriptions = []
        for char, info in self.characters.items():
            if info["count"] > 0:
                # Sử dụng mô tả đầu tiên của nhân vật
                first_desc = self.character_first_descriptions.get(char, "")
                if first_desc:
                    descriptions.append(f"character {char} ({first_desc})")
                else:
                    descriptions.append(f"character {char}")
        return ", ".join(descriptions)
    
    def get_scene_continuity(self):
        """Tạo mô tả về tính liên tục của cảnh"""
        if len(self.scene_history) > 0:
            # Lấy 2 cảnh gần nhất để tham chiếu
            recent_scenes = self.scene_history[-2:] if len(self.scene_history) >= 2 else self.scene_history
            return f"maintain visual continuity with previous scenes: {' | '.join(recent_scenes)}"
        return ""

def split_text_into_scenes(text):
    """Split text into scenes based on sentences and paragraphs"""
    # Split into sentences
    sentences = sent_tokenize(text)
    
    # Group sentences into scenes (3-4 sentences per scene)
    scenes = []
    current_scene = []
    
    for sentence in sentences:
        current_scene.append(sentence)
        if len(current_scene) >= 3:
            scenes.append(' '.join(current_scene))
            current_scene = []
    
    # Add remaining sentences
    if current_scene:
        scenes.append(' '.join(current_scene))
    
    return scenes

def translate_to_chinese(text):
    """Translate text to Chinese using Google Translate API"""
    translator = Translator()
    try:
        result = translator.translate(text, dest='zh-cn')
        return result.text
    except Exception as e:
        st.warning(f"Không thể dịch sang tiếng Trung: {str(e)}")
        return text

def translate_to_english(text):
    """Translate text to English using Google Translate API"""
    translator = Translator()
    try:
        result = translator.translate(text, dest='en')
        return result.text
    except Exception as e:
        st.warning(f"Không thể dịch sang tiếng Anh: {str(e)}")
        return text

def generate_consistent_prompt(scene_text, story_context, style, model="stable-diffusion"):
    """Tạo prompt ngắn gọn và hiệu quả"""
    # Cập nhật context với cảnh hiện tại
    story_context.update_scene(scene_text)
    
    # Xác định nhân vật chính trong cảnh hiện tại
    current_characters = []
    for char, info in story_context.characters.items():
        if len(story_context.scene_history) - 1 in info["scenes"]:
            desc = story_context.character_first_descriptions.get(char, "").strip()
            if desc:
                current_characters.append(f"{char} ({desc})")
            else:
                current_characters.append(char)
    
    # Tạo base prompt dựa trên model
    if model == "cogview":
        base_prompt = f"""场景: {scene_text}
人物: {', '.join(current_characters)}
风格: {style}风格, 高清细节, 电影级画面"""
        return base_prompt
    else:
        # Tạo prompt ngắn gọn cho Stable Diffusion
        scene_desc = translate_to_english(scene_text)
        chars = ', '.join(current_characters)
        
        prompt = f"A {style} style scene: {scene_desc}. "
        if chars:
            prompt += f"Featuring {chars}. "
        
        # Thêm yêu cầu chất lượng
        prompt += "High quality, detailed, cinematic composition, professional lighting."
        
        return prompt

def create_scene_clip(image, audio_path, duration):
    """Create a video clip from image and audio"""
    image_clip = ImageClip(np.array(image)).set_duration(duration)
    audio_clip = AudioFileClip(audio_path)
    return image_clip.set_audio(audio_clip)

def create_video(scenes, images, audio_files, output_path):
    """Create final video from scenes, images and audio"""
    clips = []
    
    for image, audio_path in zip(images, audio_files):
        # Get audio duration
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        audio_clip.close()
        
        # Create scene clip
        clip = create_scene_clip(image, audio_path, duration)
        clips.append(clip)
    
    # Concatenate all clips
    final_clip = concatenate_videoclips(clips)
    
    # Write final video
    final_clip.write_videofile(
        output_path,
        fps=24,
        codec='libx264',
        audio_codec='aac'
    )
    
    # Clean up clips
    final_clip.close()
    for clip in clips:
        clip.close()

def generate_image_cogview(prompt, style="realistic"):
    """Generate image using CogView API"""
    style_cn = {
        "realistic": "写实风格",
        "anime": "动漫风格",
        "digital art": "数字艺术",
        "oil painting": "油画风格",
        "watercolor": "水彩画风格",
        "pencil sketch": "铅笔素描",
        "3D render": "3D渲染",
        "pixel art": "像素艺术",
        "comic book": "漫画风格"
    }
    
    enhanced_prompt = f"{style_cn.get(style, '写实风格')}, {prompt}, 高质量"
    
    try:
        response = zhipuai.model_api.invoke(
            model="cogview-3-plus",
            prompt=enhanced_prompt,
            timeout=60
        )
        
        if not isinstance(response, dict):
            raise Exception(f"Invalid response format: {response}")
            
        if response.get('code') != 200 or not response.get('success'):
            error_msg = response.get('msg', 'Unknown error')
            raise Exception(f"CogView API Error: {error_msg}")
        
        data = response.get('data', {})
        if not isinstance(data, dict):
            raise Exception(f"Invalid data format: {data}")
            
        image_links = data.get('image_links', [])
        if not image_links or not isinstance(image_links, list):
            raise Exception(f"No image links received: {data}")
        
        image_url = image_links[0].get('url')
        if not image_url:
            raise Exception("Invalid image URL")
        
        image_response = requests.get(image_url, timeout=30)
        if image_response.status_code != 200:
            raise Exception(f"Failed to download image: HTTP {image_response.status_code}")
        
        return Image.open(io.BytesIO(image_response.content))
        
    except Exception as e:
        st.error(f"CogView API Debug Info:")
        st.error(f"Prompt: {enhanced_prompt}")
        if 'response' in locals():
            st.error(f"Response: {response}")
        raise Exception(f"CogView Error: {str(e)}")

def generate_image_sd(prompt, style="realistic", api_key=None):
    """Generate image using Stable Diffusion API with multiple keys"""
    if not api_key:
        api_key = SD_API_KEYS[0]
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "text_prompts": [
            {
                "text": prompt,
                "weight": 1
            },
            {
                "text": "blurry, low quality, worst quality, text, watermark, signature, deformed, distorted, disfigured, bad anatomy",
                "weight": -1
            }
        ],
        "cfg_scale": 7,
        "height": 1024,
        "width": 1024,
        "samples": 1,
        "steps": 30,
        "seed": st.session_state.get('last_seed', 42)
    }
    
    try:
        response = requests.post(
            SD_API_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Stable Diffusion API Error: {response.text}")
        
        result = response.json()
        
        if "artifacts" in result and len(result["artifacts"]) > 0:
            if 'seed' in result["artifacts"][0]:
                st.session_state['last_seed'] = result["artifacts"][0]['seed']
            
            image_data = result["artifacts"][0]["base64"]
            return Image.open(io.BytesIO(base64.b64decode(image_data)))
        
        raise Exception("Không nhận được dữ liệu hình ảnh từ API")
        
    except requests.exceptions.Timeout:
        raise Exception("API phản hồi quá chậm, vui lòng thử lại")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Lỗi kết nối: {str(e)}")

def generate_image_gemini_colab(prompt, style="realistic"):
    """Generate image using Gemini API through Google Colab"""
    try:
        # URL của Colab Notebook được expose qua ngrok
        COLAB_API_URL = os.getenv('COLAB_API_URL', '')
        if not COLAB_API_URL:
            raise Exception("Chưa cấu hình COLAB_API_URL. Vui lòng cập nhật trong file .env")

        # Tạo prompt với style
        enhanced_prompt = f"Create a {style} style image: {prompt}. High quality, detailed, professional lighting and composition."
        
        # Chuẩn bị payload
        payload = {
            "prompt": enhanced_prompt,
            "api_key": GEMINI_API_KEY,
            "style": style
        }
        
        # Gọi API của Colab notebook
        st.info("🔄 Đang kết nối với Google Colab...")
        response = requests.post(
            COLAB_API_URL + "/generate_image",
            json=payload,
            timeout=60
        )
        
        # Kiểm tra response
        if response.status_code != 200:
            raise Exception(f"Colab API Error: {response.text}")
            
        # Parse response
        result = response.json()
        if "error" in result:
            raise Exception(f"Colab Error: {result['error']}")
            
        # Lấy ảnh từ base64 string
        if "image" not in result:
            raise Exception("Không nhận được dữ liệu hình ảnh từ Colab")
            
        image_data = base64.b64decode(result["image"])
        return Image.open(BytesIO(image_data))
            
    except Exception as e:
        error_msg = str(e)
        st.error("Gemini Colab API Debug Info:")
        st.error(f"Error message: {error_msg}")
        st.error(f"Prompt used: {enhanced_prompt}")
        
        # Hỏi người dùng có muốn thử lại với model khác không
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Thử lại với Stable Diffusion"):
                return generate_image_sd(prompt, style, SD_API_KEYS[0])
        with col2:
            if st.button("🔄 Thử lại với CogView"):
                return generate_image_cogview(prompt, style)
        
        raise Exception(f"Gemini Colab Error: {error_msg}")

def generate_image(prompt, style, model="stable-diffusion"):
    """Generate image using selected model"""
    max_retries = 3
    current_try = 0
    last_error = None
    
    while current_try < max_retries:
        try:
            if model == "cogview":
                return generate_image_cogview(prompt, style)
            elif model == "gemini":
                return generate_image_gemini_colab(prompt, style)
            else:
                # Thử với tất cả API key của Stable Diffusion
                for i, api_key in enumerate(SD_API_KEYS):
                    try:
                        return generate_image_sd(prompt, style, api_key)
                    except Exception as e:
                        if "insufficient_balance" in str(e):
                            if i < len(SD_API_KEYS) - 1:
                                st.warning(f"API key {i+1} hết balance, đang thử với key tiếp theo...")
                                continue
                            else:
                                st.warning("Đã hết tất cả API key của Stable Diffusion, chuyển sang sử dụng CogView...")
                                return generate_image_cogview(prompt, style)
                        else:
                            raise e
                
                # Nếu đã thử hết các key mà vẫn không thành công
                st.warning("Không thể sử dụng Stable Diffusion, chuyển sang CogView...")
                return generate_image_cogview(prompt, style)
                
        except Exception as e:
            last_error = e
            current_try += 1
            if current_try < max_retries:
                st.warning(f"Lần thử {current_try} thất bại. Đang thử lại...")
                time.sleep(2)  # Đợi 2 giây trước khi thử lại
    
    raise last_error

if __name__ == "__main__":
    main() 