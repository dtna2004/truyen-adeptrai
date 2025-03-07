import streamlit as st
import os
import requests
import base64
from dotenv import load_dotenv
from PIL import Image
import io
from gtts import gTTS
from moviepy.editor import *
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
import tempfile
import re
import time
import json
from googletrans import Translator
import zhipuai
import numpy as np
import google.generativeai as genai
from io import BytesIO

# Download NLTK data
nltk.download('punkt')

# Load environment variables
load_dotenv()

# API Endpoints and Keys
COGVIEW_API_KEY = os.getenv('COGVIEW_API_KEY')
zhipuai.api_key = COGVIEW_API_KEY
SD_API_ENDPOINT = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
SD_API_KEYS = os.getenv('SD_API_KEYS', '').split(',')
SD_API_KEYS = [key.strip() for key in SD_API_KEYS if key.strip()]
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

# Cấu hình Gemini API
genai.configure(api_key=GEMINI_API_KEY)

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

def text_to_speech(text, lang='vi'):
    """Convert text to speech using gTTS"""
    tts = gTTS(text=text, lang=lang, slow=False)
    audio_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
    tts.save(audio_file.name)
    return audio_file.name

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

def main():
    st.set_page_config(
        page_title="Text to Video Generator",
        page_icon="🎬",
        layout="wide"
    )
    
    # Khởi tạo story context trong session state
    if 'story_context' not in st.session_state:
        st.session_state.story_context = StoryContext()
    
    st.title("🎬 Tạo Video Từ Văn Bản")
    st.write("Tải lên file văn bản để tạo video với hình ảnh và giọng đọc")
    
    # API Key management
    with st.expander("Quản lý API Keys", expanded=False):
        st.markdown("""
        ### 📝 Hướng dẫn
        - **Stable Diffusion**: Nhập mỗi API key trên một dòng
        - **CogView**: Nhập API key từ Zhipu AI
        - **Gemini**: Nhập API key từ Google AI Studio
        """)
        
        # Tạo 3 tab cho 3 loại API key
        tab1, tab2, tab3 = st.tabs(["🎨 Stable Diffusion", "🖼 CogView", "🤖 Gemini"])
        
        with tab1:
            # Load lại API keys từ file .env
            load_dotenv(override=True)
            current_sd_keys = os.getenv('SD_API_KEYS', '').split(',')
            current_sd_keys = [key.strip() for key in current_sd_keys if key.strip()]
            
            st.markdown("#### Stable Diffusion API Keys")
            sd_keys_input = st.text_area(
                "Nhập các API key, mỗi key một dòng",
                value='\n'.join(current_sd_keys),
                help="Mỗi key nên được nhập trên một dòng mới",
                key="sd_keys",
                height=150
            )
            st.caption("Số lượng key hiện tại: " + str(len(current_sd_keys)))
        
        with tab2:
            current_cogview_key = os.getenv('COGVIEW_API_KEY', '')
            
            st.markdown("#### CogView API Key")
            cogview_key_input = st.text_input(
                "Nhập API key",
                value=current_cogview_key,
                help="Nhập CogView API key từ Zhipu AI",
                key="cogview_key",
                type="password"
            )
            if current_cogview_key:
                st.caption("✅ Đã cấu hình")
            else:
                st.caption("❌ Chưa cấu hình")
        
        with tab3:
            current_gemini_key = os.getenv('GEMINI_API_KEY', '')
            
            st.markdown("#### Gemini API Key")
            st.markdown("""
            Để lấy Gemini API key:
            1. Truy cập [Google AI Studio](https://makersuite.google.com/app/apikey)
            2. Đăng nhập và tạo API key mới
            3. Copy và dán API key vào ô bên dưới
            """)
            gemini_key_input = st.text_input(
                "Nhập API key",
                value=current_gemini_key,
                help="Nhập Gemini API key từ Google AI Studio",
                key="gemini_key",
                type="password"
            )
            if current_gemini_key:
                st.caption("✅ Đã cấu hình")
            else:
                st.caption("❌ Chưa cấu hình")
        
        # Nút lưu
        if st.button("💾 Lưu Tất Cả API Keys"):
            try:
                # Xử lý và làm sạch input
                sd_keys = [key.strip() for key in sd_keys_input.strip().split('\n') if key.strip()]
                cogview_key = cogview_key_input.strip()
                gemini_key = gemini_key_input.strip()
                
                # Cập nhật file .env
                with open('.env', 'w', encoding='utf-8') as f:
                    f.write(f"SD_API_KEYS={','.join(sd_keys)}\n")
                    f.write(f"COGVIEW_API_KEY={cogview_key}\n")
                    f.write(f"GEMINI_API_KEY={gemini_key}")
                
                # Reload environment variables
                load_dotenv(override=True)
                
                # Cập nhật biến trong chương trình
                global SD_API_KEYS, COGVIEW_API_KEY, GEMINI_API_KEY
                SD_API_KEYS = sd_keys
                COGVIEW_API_KEY = cogview_key
                zhipuai.api_key = cogview_key
                GEMINI_API_KEY = gemini_key
                
                # Hiển thị thông báo thành công
                st.success("✅ Đã lưu tất cả API keys!")
                
                # Hiển thị chi tiết
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.info(f"📊 Stable Diffusion: {len(sd_keys)} key(s)")
                with col2:
                    st.info("🔑 CogView: " + ("Đã cấu hình" if cogview_key else "Chưa cấu hình"))
                with col3:
                    st.info("🔑 Gemini: " + ("Đã cấu hình" if gemini_key else "Chưa cấu hình"))
                
            except Exception as e:
                st.error(f"❌ Lỗi khi lưu API keys: {str(e)}")
    
    # Text input
    text_file = st.file_uploader("Tải lên file văn bản", type=['txt'])
    
    # Style and model selection
    col1, col2 = st.columns(2)
    
    with col1:
        style = st.selectbox(
            "Chọn phong cách hình ảnh",
            ["realistic", "anime", "digital art", "oil painting", "watercolor", 
             "pencil sketch", "3D render", "pixel art", "comic book"]
        )
    
    with col2:
        model = st.selectbox(
            "Chọn model tạo hình ảnh",
            ["stable-diffusion", "cogview", "gemini"],
            help="""
            - Stable Diffusion: Cho kết quả tốt và ổn định
            - CogView: Phù hợp với nội dung tiếng Trung
            - Gemini: API mới từ Google (đang thử nghiệm)
            """
        )
        
        # Hiển thị cảnh báo nếu chọn Gemini
        if model == "gemini":
            st.info("ℹ️ Gemini API đang trong giai đoạn thử nghiệm. Nếu gặp lỗi, hệ thống sẽ tự động chuyển sang Stable Diffusion.")
            
            # Kiểm tra API server
            try:
                api_url = os.getenv('COLAB_API_URL', 'http://localhost:5000')
                response = requests.get(api_url)
                if response.status_code == 200:
                    server_info = response.json()
                    if server_info.get('status') == 'running':
                        st.success("✅ Đã kết nối tới Gemini API server")
                    else:
                        st.error("❌ Gemini API server không hoạt động đúng")
                else:
                    st.error("❌ Không thể kết nối tới Gemini API server. Vui lòng chạy file gemini_image_api.py")
            except Exception as e:
                st.error(f"❌ Lỗi kết nối tới Gemini API server: {str(e)}")
                st.error("Vui lòng chạy file gemini_image_api.py trong terminal khác")
    
    if text_file:
        text_content = text_file.read().decode('utf-8')
        
        # Process button
        if st.button("Tạo Video"):
            try:
                # Reset story context
                st.session_state.story_context = StoryContext()
                
                # Split text into scenes
                scenes = split_text_into_scenes(text_content)
                
                # Hiển thị thông tin cảnh
                st.subheader("1. Phân tích văn bản")
                with st.expander("Chi tiết các cảnh", expanded=True):
                    for i, scene in enumerate(scenes, 1):
                        st.markdown(f"**Cảnh {i}:**")
                        st.write(scene)
                
                # Progress tracking
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Generate images with consistency
                images = []
                audio_files = []
                current_sd_key_index = 0
                
                # Container cho kết quả xử lý
                result_container = st.container()
                
                for i, scene in enumerate(scenes):
                    with result_container.expander(f"Đang xử lý cảnh {i+1}/{len(scenes)}", expanded=True):
                        status_text.text(f"Đang xử lý cảnh {i+1}/{len(scenes)}")
                        progress = (i) / len(scenes)
                        progress_bar.progress(progress)
                        
                        # Generate prompt
                        prompt = generate_consistent_prompt(
                            scene, 
                            st.session_state.story_context,
                            style,
                            model
                        )
                        
                        st.markdown("**Prompt được tạo:**")
                        st.code(prompt)
                        
                        # Thử tạo hình ảnh với cả hai model
                        success = False
                        error_messages = []
                        
                        with st.spinner("Đang tạo hình ảnh..."):
                            try:
                                image = generate_image(prompt, style, model)
                                st.success(f"✅ Đã tạo hình ảnh thành công")
                                st.image(image, use_column_width=True)
                                images.append(image)
                                success = True
                            except Exception as e:
                                error_messages.append(str(e))
                                st.error(f"❌ Không thể tạo hình ảnh: {str(e)}")
                        
                        if not success:
                            raise Exception(f"Không thể tạo hình ảnh cho cảnh {i+1}. Lỗi: {'; '.join(error_messages)}")
                        
                        # Generate audio
                        with st.spinner("Đang tạo giọng đọc..."):
                            audio_file = text_to_speech(scene)
                            audio_files.append(audio_file)
                            st.success("✅ Đã tạo giọng đọc")
                            st.audio(audio_file)
                        
                        # Update progress
                        progress = (i + 1) / len(scenes)
                        progress_bar.progress(progress)
                
                # Create and save video
                with st.spinner('Đang tạo video...'):
                    output_path = "output_video.mp4"
                    create_video(scenes, images, audio_files, output_path)
                    
                    # Display results
                    st.success("✅ Đã tạo video thành công!")
                    st.video(output_path)
                    
                    # Provide download link
                    with open(output_path, 'rb') as f:
                        st.download_button(
                            label="Tải video xuống",
                            data=f.read(),
                            file_name="story_video.mp4",
                            mime="video/mp4"
                        )
                
                # Clean up
                for audio_file in audio_files:
                    os.unlink(audio_file)
                os.unlink(output_path)
                
            except Exception as e:
                st.error(f"Lỗi trong quá trình tạo video: {str(e)}")
                if 'error_messages' in locals():
                    st.error("Chi tiết lỗi:")
                    for msg in error_messages:
                        st.error(msg)

if __name__ == "__main__":
    main() 