from flask import Flask, render_template, jsonify, send_from_directory
import json
import os

app = Flask(__name__)

# Đường dẫn tới thư mục static và templates
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stories')
def get_stories():
    stories_file = os.path.join(STATIC_DIR, 'stories.json')
    if os.path.exists(stories_file):
        with open(stories_file, 'r', encoding='utf-8') as f:
            stories = json.load(f)
        return jsonify(stories)
    return jsonify([])

@app.route('/story/<story_id>')
def story_detail(story_id):
    stories_file = os.path.join(STATIC_DIR, 'stories.json')
    if os.path.exists(stories_file):
        with open(stories_file, 'r', encoding='utf-8') as f:
            stories = json.load(f)
            story = next((s for s in stories if s['id'] == story_id), None)
            if story:
                return render_template('story.html', story=story)
    return "Không tìm thấy truyện", 404

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory(STATIC_DIR, path)

# Tạo file stories.json nếu chưa tồn tại
def init_stories_file():
    stories_file = os.path.join(STATIC_DIR, 'stories.json')
    if not os.path.exists(stories_file):
        os.makedirs(STATIC_DIR, exist_ok=True)
        with open(stories_file, 'w', encoding='utf-8') as f:
            json.dump([], f)

# Khởi tạo khi khởi động app
init_stories_file()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 