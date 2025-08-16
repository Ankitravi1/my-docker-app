import os
import uuid
import threading
from flask import Flask, request, render_template, jsonify, url_for, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import video_processor

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

# In-memory store for task status. In a real app, you'd use a database or Redis.
tasks = {}

def get_file_path(folder, filename):
    return os.path.join(folder, filename)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    if request.method == 'POST':
        try:
            # --- Form Data ---
            project_title = request.form.get('project_title', 'default-project')
            font = request.form.get('font', 'Arial')
            font_color = request.form.get('font_color', '#FFFFFF')
            # Backward compatibility: original single vertical position slider was named 'position'
            position_vertical = int(request.form.get('position_vertical', request.form.get('position', 10)))
            position_horizontal = request.form.get('position_horizontal', 'center')
            font_size = int(request.form.get('font_size', 48))
            # Checkbox semantics: when checked browsers send 'on'; when unchecked it's absent.
            raw_caption_auto = request.form.get('caption_auto')
            caption_auto = False
            if raw_caption_auto is not None:
                caption_auto = str(raw_caption_auto).strip().lower() in ('on', 'true', '1', 'yes')

            # --- File Handling ---
            if 'audio' not in request.files or 'images' not in request.files:
                return jsonify({'status': 'error', 'message': 'Audio and image files are required.'}), 400

            audio_file = request.files['audio']
            image_files = request.files.getlist('images')
            srt_file = request.files.get('srt')

            if audio_file.filename == '' or not any(f.filename for f in image_files):
                return jsonify({'status': 'error', 'message': 'No selected file.'}), 400

            # --- Task Setup ---
            task_id = uuid.uuid4().hex
            tasks[task_id] = {
                'status': 'starting',
                'logs': ['Task initiated...'],
                'progress': 0,
                'steps': [],
            }

            # --- Project Setup ---
            project_id = f"{secure_filename(project_title)}-{task_id[:8]}"
            project_output_dir = get_file_path(app.config['OUTPUT_FOLDER'], project_id)
            os.makedirs(project_output_dir, exist_ok=True)

            # --- Save Uploads ---
            audio_filename = secure_filename(audio_file.filename)
            audio_path = get_file_path(app.config['UPLOAD_FOLDER'], audio_filename)
            audio_file.save(audio_path)

            image_paths = []
            for image in image_files:
                image_filename = secure_filename(image.filename)
                image_path = get_file_path(app.config['UPLOAD_FOLDER'], image_filename)
                image.save(image_path)
                image_paths.append(image_path)

            # Optional SRT upload
            srt_path = None
            if srt_file and srt_file.filename:
                srt_filename = secure_filename(srt_file.filename)
                srt_path = get_file_path(app.config['UPLOAD_FOLDER'], srt_filename)
                srt_file.save(srt_path)

            # --- Video Generation Config ---
            output_video_filename = f"{project_id}.mp4"
            output_video_path = get_file_path(project_output_dir, output_video_filename)

            # Build a proper download URL via a Flask route
            video_url = url_for('download_video', task_id=task_id, _external=True)


            config = {
                "audio_path": audio_path,
                "image_paths": image_paths,
                "output_path": output_video_path,
                "font": font,
                "font_color": font_color,
                "font_size": font_size,
                "position_vertical_percent": position_vertical / 100.0,
                "position_horizontal": position_horizontal,
                "assemblyai_api_key": os.getenv("ASSEMBLYAI_API_KEY"),
                "use_auto_captions": caption_auto,
                "srt_path": srt_path,
                "video_url": video_url,
            }

            # Store project information on the task for download
            tasks[task_id]['project_id'] = project_id
            tasks[task_id]['output_video_filename'] = output_video_filename

            # --- Run video creation in a background thread ---
            thread = threading.Thread(target=video_processor.create_video, args=(task_id, tasks, config))
            thread.start()

            return jsonify({
                'status': 'success',
                'message': 'Video generation started!',
                'task_id': task_id
            })

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/status/<task_id>')
def task_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404
    return jsonify(task)

@app.route('/download/<task_id>')
def download_video(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404
    if task.get('status') != 'completed':
        return jsonify({'status': 'error', 'message': 'Video not ready for download'}), 400
    project_id = task.get('project_id')
    filename = task.get('output_video_filename')
    if not project_id or not filename:
        return jsonify({'status': 'error', 'message': 'Download info missing'}), 500
    directory = os.path.join(app.config['OUTPUT_FOLDER'], project_id)
    if not os.path.exists(os.path.join(directory, filename)):
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
    return send_from_directory(directory=directory, path=filename, as_attachment=True)


if __name__ == '__main__':
    for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
        os.makedirs(folder, exist_ok=True)
    app.run(debug=True)
