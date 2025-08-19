import os
import uuid
import threading
from flask import Flask, request, render_template, jsonify, url_for, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import video_processor
import utils

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
            font_size = int(request.form.get('font_size', 48))
            aspect_ratio = request.form.get('aspect_ratio', '9:16')
            drive_link = request.form.get('drive_link', '').strip()
            # Checkbox semantics: when checked browsers send 'on'; when unchecked it's absent.
            raw_caption_auto = request.form.get('caption_auto')
            caption_auto = False
            if raw_caption_auto is not None:
                caption_auto = str(raw_caption_auto).strip().lower() in ('on', 'true', '1', 'yes')

            # Background music option (default True)
            raw_bgm = request.form.get('background_music')
            background_music_enabled = True
            if raw_bgm is not None:
                background_music_enabled = str(raw_bgm).strip().lower() in ('on', 'true', '1', 'yes')

            # Background music level percent (allowed: 4,6,8,10,12). Default 4.
            raw_bgm_level = request.form.get('background_music_level', '4')
            try:
                bgm_level = int(str(raw_bgm_level).strip())
            except Exception:
                bgm_level = 4
            if bgm_level not in {4, 6, 8, 10, 12}:
                bgm_level = 4

            # --- File Handling ---
            # Allow either: (a) Google Drive link, or (b) uploaded audio + images
            if not drive_link and ('audio' not in request.files or 'images' not in request.files):
                return jsonify({'status': 'error', 'message': 'Provide a Google Drive folder link or upload audio and images.'}), 400

            audio_file = request.files.get('audio')
            image_files = request.files.getlist('images') if 'images' in request.files else []
            srt_file = request.files.get('srt')

            if not drive_link:
                if (not audio_file or audio_file.filename == '') or (not any(f.filename for f in image_files)):
                    return jsonify({'status': 'error', 'message': 'No selected file.'}), 400

            # --- Task Setup ---
            task_id = uuid.uuid4().hex
            tasks[task_id] = {
                'status': 'starting',
                'logs': ['Task initiated...'],
                'progress': 0,
                'steps': [
                    {'key': 'retrieve', 'label': 'Retrieving folder contents', 'state': 'pending'},
                    {'key': 'build_dir', 'label': 'Building directory structure', 'state': 'pending'},
                    {'key': 'download', 'label': 'Downloading', 'state': 'pending'},
                ],
            }

            def set_step_state(task_id_local, key, state):
                for s in tasks[task_id_local].get('steps', []):
                    if s['key'] == key:
                        s['state'] = state
                        return
            def log(task_id_local, message, progress=None):
                tasks[task_id_local]['logs'].append(message)
                if isinstance(progress, (int, float)):
                    tasks[task_id_local]['progress'] = int(progress)

            # --- Project Setup ---
            project_id = f"{secure_filename(project_title)}-{task_id[:8]}"
            project_output_dir = get_file_path(app.config['OUTPUT_FOLDER'], project_id)
            os.makedirs(project_output_dir, exist_ok=True)

            # --- Resolve Inputs (Drive or Uploads) ---
            audio_path = None
            image_paths = []
            temp_dir = None  # for Drive downloads cleanup
            temp_files = []  # for direct uploads cleanup

            if drive_link:
                # Download assets from Google Drive folder
                log(task_id, 'Retrieving folder contents...', progress=1)
                set_step_state(task_id, 'retrieve', 'in_progress')
                download_dir = get_file_path(app.config['UPLOAD_FOLDER'], f"{project_id}_drive")
                set_step_state(task_id, 'build_dir', 'in_progress')
                log(task_id, 'Building directory structure...', progress=3)
                utils.ensure_dir(download_dir)
                set_step_state(task_id, 'build_dir', 'done')
                log(task_id, 'Building directory structure completed', progress=5)
                set_step_state(task_id, 'download', 'in_progress')
                log(task_id, 'Downloading...', progress=8)
                utils.download_drive_folder(drive_link, download_dir)
                utils.extract_zip_files_in_dir(download_dir)
                audio_path_drive, image_paths_drive = utils.collect_assets(download_dir)
                set_step_state(task_id, 'download', 'done')
                set_step_state(task_id, 'retrieve', 'done')
                log(task_id, 'Retrieving folder contents completed', progress=10)
                if not audio_path_drive or not image_paths_drive:
                    return jsonify({'status': 'error', 'message': 'No audio/images found in the provided Drive folder.'}), 400
                audio_path = audio_path_drive
                image_paths = image_paths_drive
                temp_dir = download_dir
            else:
                # Save uploaded files
                set_step_state(task_id, 'build_dir', 'in_progress')
                log(task_id, 'Building directory structure...', progress=3)
                audio_filename = secure_filename(audio_file.filename)
                audio_path = get_file_path(app.config['UPLOAD_FOLDER'], audio_filename)
                audio_file.save(audio_path)
                temp_files.append(audio_path)
                set_step_state(task_id, 'build_dir', 'done')
                log(task_id, 'Building directory structure completed', progress=5)

                for image in image_files:
                    image_filename = secure_filename(image.filename)
                    image_path = get_file_path(app.config['UPLOAD_FOLDER'], image_filename)
                    image.save(image_path)
                    image_paths.append(image_path)
                    temp_files.append(image_path)
                set_step_state(task_id, 'retrieve', 'done')
                set_step_state(task_id, 'download', 'done')
                log(task_id, 'Retrieving folder contents completed', progress=10)

            # Optional SRT upload
            srt_path = None
            if srt_file and srt_file.filename:
                srt_filename = secure_filename(srt_file.filename)
                srt_path = get_file_path(app.config['UPLOAD_FOLDER'], srt_filename)
                srt_file.save(srt_path)
                # treat uploaded SRT as temp file as well
                temp_files.append(srt_path)

            # --- Video Generation Config ---
            output_video_filename = f"{project_id}.mp4"
            output_video_path = get_file_path(project_output_dir, output_video_filename)

            # Build a proper download URL via a Flask route (relative path for same-origin fetch)
            video_url = url_for('download_video', task_id=task_id, _external=False)


            # Compute vertical caption position percent: force 20% for 16:9; otherwise use slider
            if aspect_ratio == '16:9':
                position_vertical_percent = 0.20
                # Force font size for widescreen
                font_size = 60
            else:
                position_vertical_percent = position_vertical / 100.0

            # Resolve background music path: env override or default to resource/Pulsar.mp3
            default_bgm_path = os.path.join(app.root_path, 'resource', 'Pulsar.mp3')
            bgm_path = os.getenv('BGM_PATH', default_bgm_path)

            config = {
                "audio_path": audio_path,
                "image_paths": image_paths,
                "output_path": output_video_path,
                "font": font,
                "font_color": font_color,
                "font_size": font_size,
                "position_vertical_percent": position_vertical_percent,
                "assemblyai_api_key": os.getenv("ASSEMBLYAI_API_KEY"),
                "use_auto_captions": caption_auto,
                "srt_path": srt_path,
                "video_url": video_url,
                "aspect_ratio": aspect_ratio,
                "temp_dir": temp_dir,
                "temp_files": temp_files,
                "background_music_enabled": background_music_enabled,
                "background_music_path": bgm_path,
                "background_music_level_percent": bgm_level,
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
    # Disable conditional and range requests to avoid 206 partial responses on first request
    resp = send_from_directory(directory=directory, path=filename, as_attachment=True, conditional=False)
    resp.headers['Accept-Ranges'] = 'none'
    # Disable caching to prevent browsers from caching transient 400/404 and to ensure fresh file
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    resp.headers['Content-Type'] = 'video/mp4'
    return resp


if __name__ == '__main__':
    for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
        os.makedirs(folder, exist_ok=True)
    # Disable the auto-reloader to avoid losing in-memory `tasks` on restarts
    # This prevents issues like "Task not found" during long background jobs when watchdog triggers
    app.run(debug=True, use_reloader=False)
