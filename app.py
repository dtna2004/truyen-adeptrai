from flask import Flask, render_template, jsonify, send_from_directory
import json
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stories')
def get_stories():
    stories_file = 'static/stories.json'
    if os.path.exists(stories_file):
        with open(stories_file, 'r', encoding='utf-8') as f:
            stories = json.load(f)
        return jsonify(stories)
    return jsonify([])

@app.route('/story/<story_id>')
def story_detail(story_id):
    stories_file = 'static/stories.json'
    if os.path.exists(stories_file):
        with open(stories_file, 'r', encoding='utf-8') as f:
            stories = json.load(f)
            story = next((s for s in stories if s['id'] == story_id), None)
            if story:
                return render_template('story.html', story=story)
    return "Không tìm thấy truyện", 404

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    app.run(debug=True, port=5000) 