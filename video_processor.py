from moviepy.editor import (AudioFileClip, ImageClip, concatenate_videoclips, TextClip, vfx)
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from PIL import Image
from proglog import ProgressBarLogger
import assemblyai as aai
import os
import platform

# --- Fix for Windows ImageMagick path ---
# If you are on Windows, moviepy might not find the ImageMagick binary automatically.
# Replace the path below with the correct path to your ImageMagick 'magick.exe' file.
# Example: r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"
if platform.system() == "Windows":
    from moviepy.config import change_settings
    # IMPORTANT: Update this path to your actual ImageMagick installation if it's different.
    change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"})

def update_status(task_id, tasks, status, log_message, progress=None):
    tasks[task_id]['status'] = status
    tasks[task_id]['logs'].append(log_message)
    if progress is not None:
        tasks[task_id]['progress'] = int(progress)
    print(f"Task {task_id} - Status: {status}, Progress: {tasks[task_id].get('progress')}%, Log: {log_message}")

def init_steps(task_id, tasks):
    steps = [
        {'key': 'init', 'label': 'Initialize', 'state': 'in_progress'},
        {'key': 'durations', 'label': 'Calculate Durations', 'state': 'pending'},
        {'key': 'images', 'label': 'Process Images', 'state': 'pending'},
        {'key': 'assemble', 'label': 'Assemble Clips', 'state': 'pending'},
        {'key': 'subtitles', 'label': 'Generate Subtitles', 'state': 'pending'},
        {'key': 'export', 'label': 'Export Video', 'state': 'pending'},
        {'key': 'cleanup', 'label': 'Cleanup', 'state': 'pending'},
    ]
    tasks[task_id]['steps'] = steps
    # Initialize export progress tracking
    tasks[task_id]['export_progress'] = 0

def set_step_state(task_id, tasks, key, state):
    for s in tasks[task_id].get('steps', []):
        if s['key'] == key:
            s['state'] = state
            return

def crop_to_9_16(image_path, output_size=(1080, 1920)):
    """
    Crops an image to a 9:16 aspect ratio, trying to keep the center.
    """
    img = Image.open(image_path)
    img_width, img_height = img.size
    target_aspect = 9.0 / 16.0
    img_aspect = float(img_width) / float(img_height)

    if img_aspect > target_aspect:
        # Image is wider than target, crop width
        new_width = int(target_aspect * img_height)
        offset = (img_width - new_width) / 2
        box = (offset, 0, img_width - offset, img_height)
    else:
        # Image is taller than target, crop height
        new_height = int(img_width / target_aspect)
        offset = (img_height - new_height) / 2
        box = (0, offset, img_width, img_height - offset)

    cropped_img = img.crop(box)
    resized_img = cropped_img.resize(output_size, Image.LANCZOS)
    
    # Save the cropped image to a temporary path to be used by MoviePy
    temp_path = os.path.splitext(image_path)[0] + '_cropped.png'
    resized_img.save(temp_path)
    return temp_path

def ken_burns_effect(clip, duration, zoom_factor=0.1):
    """
    Applies a slow zoom-in effect to a clip.
    """
    def effect(t):
        # This will zoom from 1 to 1 + zoom_factor over the duration
        return 1 + (zoom_factor * (t / duration))

    return clip.fx(vfx.resize, effect).set_position(('center', 'center'))

def create_video(task_id, tasks, config):
    """
    Generates a video based on the provided configuration.
    """
    update_status(task_id, tasks, "processing", "Video processing started...", progress=0)
    init_steps(task_id, tasks)

    cropped_image_paths = [] # Initialize here to ensure it's always defined for cleanup

    try:
        # --- Initialization ---
        audio_path = config.get("audio_path")
        image_paths = config.get("image_paths", [])
        output_path = config.get("output_path")
        font = config.get("font", "Arial")
        font_color = config.get("font_color", "white")
        font_size = int(config.get("font_size", 48))
        position_vertical_percent = float(config.get("position_vertical_percent", 0.1))
        # Horizontal position removed; captions will be centered
        assemblyai_api_key = config.get("assemblyai_api_key")
        use_auto_captions = bool(config.get("use_auto_captions", True))
        provided_srt_path = config.get("srt_path")
        video_url = config.get("video_url")

        if not all([audio_path, image_paths, output_path]):
            raise ValueError("Missing required configuration for video creation.")

        set_step_state(task_id, tasks, 'init', 'done')
        set_step_state(task_id, tasks, 'durations', 'in_progress')
        update_status(task_id, tasks, "processing", "Calculating scene durations...", progress=10)
        # --- Scene Calculation ---
        audio_clip = AudioFileClip(audio_path)
        scene_duration = audio_clip.duration / len(image_paths)

        set_step_state(task_id, tasks, 'durations', 'done')
        set_step_state(task_id, tasks, 'images', 'in_progress')
        update_status(task_id, tasks, "processing", "Processing images and applying Ken Burns effect...", progress=25)
        # --- Image Processing & Animation ---
        video_clips = []
        for img_path in image_paths:
            cropped_path = crop_to_9_16(img_path)
            cropped_image_paths.append(cropped_path)
            
            img_clip = ImageClip(cropped_path).set_duration(scene_duration)
            animated_clip = ken_burns_effect(img_clip, scene_duration)
            video_clips.append(animated_clip)

        set_step_state(task_id, tasks, 'images', 'done')
        set_step_state(task_id, tasks, 'assemble', 'in_progress')
        update_status(task_id, tasks, "processing", "Assembling video clips...", progress=45)
        # --- Video Assembly ---
        final_clip = concatenate_videoclips(video_clips, method="compose").set_audio(audio_clip)

        # --- Subtitle Generation ---
        set_step_state(task_id, tasks, 'assemble', 'done')
        set_step_state(task_id, tasks, 'subtitles', 'in_progress')

        subtitles = None  # legacy var (no longer used for word-by-word)
        srt_path = None
        overlay_clips = []  # holds per-word TextClip overlays

        # Prepare transcription (for auto) or set SRT path if provided
        if provided_srt_path:
            srt_path = provided_srt_path
            update_status(task_id, tasks, "processing", "Using provided SRT for subtitles...", progress=55)
        elif use_auto_captions and assemblyai_api_key:
            update_status(task_id, tasks, "processing", "Transcribing with AssemblyAI for word timings...", progress=55)
            aai.settings.api_key = assemblyai_api_key
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(audio_path)
            if transcript.status == aai.TranscriptStatus.error:
                error_message = f"AssemblyAI Error: {transcript.error}"
                # mark subtitles step as error but continue without subtitles
                set_step_state(task_id, tasks, 'subtitles', 'error')
                update_status(task_id, tasks, "processing", error_message, progress=60)
        else:
            update_status(task_id, tasks, "processing", "Skipping captions (no SRT and auto disabled or API key missing).", progress=55)

        try:
            if provided_srt_path:
                # Parse SRT and split each subtitle interval evenly across words
                def parse_time_to_sec(t):
                    # format: HH:MM:SS,mmm
                    h, m, rest = t.split(":")
                    s, ms = rest.split(",")
                    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

                with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                entries = []
                for block in content.strip().split("\n\n"):
                    lines = [ln for ln in block.splitlines() if ln.strip()]
                    if (len(lines) >= 2 and "-->" in lines[0]) or (len(lines) >= 3 and "-->" in lines[1]):
                        # handle optional index line
                        time_line = lines[0] if "-->" in lines[0] else lines[1]
                        text_lines = lines[1:] if time_line is lines[0] else lines[2:]
                        start_str, end_str = [x.strip() for x in time_line.split("-->")]
                        start = parse_time_to_sec(start_str)
                        end = parse_time_to_sec(end_str)
                        text = " ".join(text_lines).strip()
                        if start < end and text:
                            entries.append((start, end, text))

                # Compute vertical relative y (0=top, 1=bottom). Slider is distance from bottom.
                rel_y = 1.0 - max(0.0, min(1.0, position_vertical_percent))

                for (start, end, text) in entries:
                    words = [w for w in text.split() if w]
                    if not words:
                        continue
                    total = len(words)
                    dur = max(0.01, end - start)
                    slice_dur = dur / total
                    t0 = start
                    for w in words:
                        t1 = t0 + slice_dur
                        clip = TextClip(
                            w,
                            font=font,
                            fontsize=font_size,
                            color=font_color,
                            stroke_color='black',
                            stroke_width=4,
                            method='caption',
                            align='center',
                            size=(final_clip.w, None)
                        )
                        clip = clip.set_start(t0).set_end(t1).set_position(('center', rel_y), relative=True)
                        overlay_clips.append(clip)
                        t0 = t1
                set_step_state(task_id, tasks, 'subtitles', 'done')

            elif use_auto_captions and assemblyai_api_key:
                # Already transcribed above if enabled; use word timestamps
                if 'transcript' in locals() and transcript and getattr(transcript, 'words', None):
                    # Compute vertical relative y (0=top, 1=bottom). Slider is distance from bottom.
                    rel_y = 1.0 - max(0.0, min(1.0, position_vertical_percent))
                    for w in transcript.words:
                        # AssemblyAI word times are ms
                        start = (w.start or 0) / 1000.0
                        end = (w.end or (w.start or 0)) / 1000.0
                        if end <= start:
                            end = start + 0.05
                        txt = (w.text or '').strip()
                        if not txt:
                            continue
                        clip = TextClip(
                            txt,
                            font=font,
                            fontsize=font_size,
                            color=font_color,
                            stroke_color='black',
                            stroke_width=4,
                            method='caption',
                            align='center',
                            size=(final_clip.w, None)
                        )
                        clip = clip.set_start(start).set_end(end).set_position(('center', rel_y), relative=True)
                        overlay_clips.append(clip)
                set_step_state(task_id, tasks, 'subtitles', 'done')
            else:
                # No subtitles
                set_step_state(task_id, tasks, 'subtitles', 'done')
        except Exception as sub_e:
            # Fail gracefully on subtitle overlay generation
            set_step_state(task_id, tasks, 'subtitles', 'error')
            update_status(task_id, tasks, "processing", f"Subtitle overlay error: {sub_e}", progress=60)

        set_step_state(task_id, tasks, 'export', 'in_progress')
        update_status(task_id, tasks, "processing", "Compositing and exporting final video...", progress=70)
        # --- Final Composition ---
        class ExportLogger(ProgressBarLogger):
            def bars_callback(self, bar, attr, value, old_value=None):
                # bar 't' is the main tqdm bar in MoviePy exports
                if bar == 't':
                    total = self.bars[bar].get('total') or 0
                    index = self.bars[bar].get('index') or 0
                    pct = 0
                    if total:
                        pct = int(100 * index / total)
                    tasks[task_id]['export_progress'] = pct
        export_logger = ExportLogger()
        tasks[task_id]['export_progress'] = 0
        if overlay_clips:
            video_with_overlays = CompositeVideoClip([final_clip] + overlay_clips)
            video_with_overlays.write_videofile(output_path, codec='libx264', audio_codec='aac', fps=24, threads=4, logger=export_logger)
        else:
            final_clip.write_videofile(output_path, codec='libx264', audio_codec='aac', fps=24, threads=4, logger=export_logger)

        set_step_state(task_id, tasks, 'export', 'done')
        update_status(task_id, tasks, "completed", f"Video created successfully.", progress=100)
        tasks[task_id]['video_url'] = video_url # Store the URL for frontend

    except Exception as e:
        error_message = f"An error occurred during video processing: {e}"
        set_step_state(task_id, tasks, 'export', 'error')
        update_status(task_id, tasks, "error", error_message)
    finally:
        # --- Cleanup --- 
        set_step_state(task_id, tasks, 'cleanup', 'in_progress')
        update_status(task_id, tasks, tasks[task_id]['status'], "Cleaning up temporary files...", progress=tasks[task_id].get('progress'))
        for path in cropped_image_paths:
            if os.path.exists(path):
                os.remove(path)
        # Also remove the original uploads if they are no longer needed
        # (Assuming they are in a temp location managed by the main app)
        set_step_state(task_id, tasks, 'cleanup', 'done')
