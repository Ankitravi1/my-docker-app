from moviepy.editor import (AudioFileClip, ImageClip, VideoFileClip, ColorClip, concatenate_videoclips, TextClip, vfx, CompositeAudioClip)
from moviepy.audio.fx.all import audio_loop
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from PIL import Image
from proglog import ProgressBarLogger
import shutil
import assemblyai as aai
import os
import platform
import re

# --- Fix for Windows ImageMagick path ---
# If you are on Windows, moviepy might not find the ImageMagick binary automatically.
# Replace the path below with the correct path to your ImageMagick 'magick.exe' file.
# Example: r"C:\\Program Files\\ImageMagick-7.1.1-Q16-HDRI\\magick.exe"
if platform.system() == "Windows":
    from moviepy.config import change_settings
    # Prefer env var if provided, otherwise fall back to a common default
    imagemagick_bin = os.getenv("IMAGEMAGICK_BINARY", r"C:\\Program Files\\ImageMagick-7.1.2-Q16-HDRI\\magick.exe")
    change_settings({"IMAGEMAGICK_BINARY": imagemagick_bin})

# --- Caption tuning constants ---
CAPTION_MIN_WORDS_16_9 = 5
CAPTION_MAX_WORDS_16_9 = 8
CAPTION_PAUSE_BREAK_S = 0.6  # pause length to split sentences for auto captions

def chunk_tokens(tokens, min_words=CAPTION_MIN_WORDS_16_9, max_words=CAPTION_MAX_WORDS_16_9):
    """Chunk tokens into groups up to max_words and rebalance last chunk to satisfy min_words when possible."""
    n = len(tokens)
    if n == 0:
        return []
    chunks = []
    i = 0
    while i < n:
        j = min(i + max_words, n)
        chunks.append(tokens[i:j])
        i = j
    if len(chunks) >= 2 and len(chunks[-1]) < min_words:
        deficit = min_words - len(chunks[-1])
        take = min(deficit, max(0, len(chunks[-2]) - min_words))
        if take > 0:
            moved = chunks[-2][-take:]
            chunks[-2] = chunks[-2][:-take]
            chunks[-1] = moved + chunks[-1]
    return chunks

def make_text_clip(text, start, end, final_clip, font, font_size, font_color, rel_y):
    """
    Build a readable caption with:
    - Anti-aliased text (ImageMagick default via MoviePy TextClip)
    - Subtle shadow (2px offset, ~0.6 opacity)
    - Semi-transparent background for contrast
    """
    # Base text (no heavy stroke for cleaner anti-aliased edges)
    txt = TextClip(
        text,
        font=font,
        fontsize=font_size,
        color=font_color,
        stroke_color=None,
        stroke_width=0,
        method='label',  # tight surface around text; no full-width container
        align='center'
    ).set_duration(max(0.01, end - start))

    # Shadow: a darker duplicate, slightly offset
    shadow = TextClip(
        text,
        font=font,
        fontsize=font_size,
        color='black',
        stroke_color=None,
        stroke_width=0,
        method='label',
        align='center'
    ).set_opacity(0.6).set_duration(txt.duration)

    # Background: semi-transparent black panel with small padding
    tw, th = txt.size
    pad = max(8, int(font_size * 0.25))
    bg = ColorClip(size=(tw + 2 * pad, th + 2 * pad), color=(0, 0, 0)).set_opacity(0.35).set_duration(txt.duration)

    # Compose: background, shadow (offset), then text
    shadow_offset = (pad + 2, pad + 2)
    txt_offset = (pad, pad)
    composed = CompositeVideoClip([
        bg,
        shadow.set_position(shadow_offset),
        txt.set_position(txt_offset)
    ])

    return composed.set_start(start).set_end(end).set_position(('center', rel_y), relative=True)

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
    existing = tasks[task_id].get('steps', [])
    tasks[task_id]['steps'] = existing + steps
    # Initialize export progress tracking
    tasks[task_id]['export_progress'] = 0

def set_step_state(task_id, tasks, key, state):
    for s in tasks[task_id].get('steps', []):
        if s['key'] == key:
            s['state'] = state
            return

def crop_to_aspect(image_path, aspect_ratio='9:16'):
    """
    Crop an image to the requested aspect ratio ('9:16' or '16:9') and resize to a
    standard output size for that ratio. Returns a temp PNG path for MoviePy.
    """
    if aspect_ratio == '16:9':
        target_aspect = 16.0 / 9.0
        output_size = (1920, 1080)
    else:
        target_aspect = 9.0 / 16.0
        output_size = (1080, 1920)

    img = Image.open(image_path)
    img_width, img_height = img.size
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

    temp_path = os.path.splitext(image_path)[0] + f'_cropped_{aspect_ratio.replace(":","x")}.png'
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
    update_status(task_id, tasks, "processing", "Video processing started...", progress=1)
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
        aspect_ratio = config.get("aspect_ratio", "9:16")
        transition_duration = float(config.get("transition_duration", 0.7))
        background_music_enabled = bool(config.get("background_music_enabled", True))
        background_music_path = config.get("background_music_path")
        # User-selected level percent for background music
        try:
            bgm_level_percent = int(config.get("background_music_level_percent", 4))
        except Exception:
            bgm_level_percent = 4
        if bgm_level_percent not in {4, 6, 8, 10, 12}:
            bgm_level_percent = 4

        if not all([audio_path, image_paths, output_path]):
            raise ValueError("Missing required configuration for video creation.")

        set_step_state(task_id, tasks, 'init', 'done')
        set_step_state(task_id, tasks, 'durations', 'in_progress')
        update_status(task_id, tasks, "processing", "Calculating scene durations...", progress=3)
        # --- Scene Calculation ---
        audio_clip = AudioFileClip(audio_path)
        total_audio = audio_clip.duration
        # Prepare background music if enabled
        bgm_clip = None
        try:
            if background_music_enabled and background_music_path and os.path.exists(background_music_path):
                raw_bgm = AudioFileClip(background_music_path)
                if raw_bgm.duration >= total_audio:
                    bgm_clip = raw_bgm.subclip(0, total_audio)
                else:
                    bgm_clip = audio_loop(raw_bgm, duration=total_audio)
                # Set background music volume based on selected percent
                bgm_clip = bgm_clip.volumex(bgm_level_percent / 100.0)
        except Exception:
            # If anything goes wrong with BGM, proceed without it
            bgm_clip = None
        # Natural sort image paths by numeric filename (e.g., 0.jpg, 1.png, ...)
        def numeric_key(p):
            base = os.path.splitext(os.path.basename(p))[0]
            return (0, int(base)) if base.isdigit() else (1, base)
        image_paths = sorted(image_paths, key=numeric_key)

        num_images = len(image_paths)
        # Rule 1: exact per-image duration
        scene_duration = total_audio / max(1, num_images)

        set_step_state(task_id, tasks, 'durations', 'done')
        set_step_state(task_id, tasks, 'images', 'in_progress')
        update_status(task_id, tasks, "processing", "Processing images (crop to aspect) and applying Ken Burns...", progress=5)
        # --- Image Processing & Animation ---
        video_clips = []
        for img_path in image_paths:
            cropped_path = crop_to_aspect(img_path, aspect_ratio=aspect_ratio)
            cropped_image_paths.append(cropped_path)
            
            img_clip = ImageClip(cropped_path).set_duration(scene_duration)
            animated_clip = ken_burns_effect(img_clip, scene_duration)
            video_clips.append(animated_clip)

        set_step_state(task_id, tasks, 'images', 'done')
        set_step_state(task_id, tasks, 'assemble', 'in_progress')
        update_status(task_id, tasks, "processing", "Assembling video clips with transitions...", progress=7)
        # --- Video Assembly with non-overlapping fade transitions ---
        # Rule 2: transitions must fit within each clip's duration and not extend it.
        # We'll apply fade in/out per clip (no overlap) and concatenate.
        # Cap transition to at most half the scene duration.
        eff_transition = max(0.0, min(transition_duration, scene_duration / 2.0))
        faded_clips = []
        for idx, clip in enumerate(video_clips):
            c = clip
            if eff_transition > 0:
                # Fade in at start and fade out at end; keep duration unchanged
                c = c.fx(vfx.fadein, eff_transition).fx(vfx.fadeout, eff_transition)
            faded_clips.append(c)
        base_clip = concatenate_videoclips(faded_clips, method="compose")
        # Rule 1: Ensure final duration equals audio duration exactly (account for rounding)
        base_clip = base_clip.set_duration(total_audio)
        # Attach audio: main at 100% plus optional background at 20%
        if bgm_clip is not None:
            mixed_audio = CompositeAudioClip([audio_clip.volumex(1.0), bgm_clip])
            final_clip = base_clip.set_audio(mixed_audio)
        else:
            final_clip = base_clip.set_audio(audio_clip)

        # --- Subtitle Generation ---
        set_step_state(task_id, tasks, 'assemble', 'done')
        set_step_state(task_id, tasks, 'subtitles', 'in_progress')

        # removed unused legacy variable 'subtitles'
        srt_path = None
        overlay_clips = []  # holds per-word TextClip overlays

        # Prepare transcription (for auto) or set SRT path if provided
        if provided_srt_path:
            srt_path = provided_srt_path
            update_status(task_id, tasks, "processing", "Using provided SRT for subtitles...", progress=9)
        elif use_auto_captions and assemblyai_api_key:
            update_status(task_id, tasks, "processing", "Transcribing with AssemblyAI for word timings...", progress=9)
            aai.settings.api_key = assemblyai_api_key
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(audio_path)
            if transcript.status == aai.TranscriptStatus.error:
                error_message = f"AssemblyAI Error: {transcript.error}"
                # mark subtitles step as error but continue without subtitles
                set_step_state(task_id, tasks, 'subtitles', 'error')
                update_status(task_id, tasks, "processing", error_message, progress=60)
        else:
            update_status(task_id, tasks, "processing", "Skipping captions (no SRT and auto disabled or API key missing).", progress=9)

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
                    dur = max(0.01, end - start)
                    if aspect_ratio == '16:9':
                        # Chunk long sentences into ~5-8 words per segment with proportional timing
                        words = [w for w in text.split() if w]
                        total_words = len(words)
                        if total_words == 0:
                            continue
                        chunks = chunk_tokens(words)
                        total_dur = max(0.01, dur)
                        acc = start
                        for ch in chunks:
                            ch_text = " ".join(ch)
                            ch_fraction = len(ch) / float(total_words)
                            ch_dur = max(0.05, total_dur * ch_fraction)
                            ch_start = acc
                            ch_end = min(end, ch_start + ch_dur)
                            acc = ch_end
                            overlay_clips.append(
                                make_text_clip(ch_text, ch_start, ch_end, final_clip, font, font_size, font_color, rel_y)
                            )
                    else:
                        # Word-by-word for vertical formats
                        total = len(words)
                        slice_dur = dur / total
                        t0 = start
                        for w in words:
                            t1 = t0 + slice_dur
                            overlay_clips.append(
                                make_text_clip(w, t0, t1, final_clip, font, font_size, font_color, rel_y)
                            )
                            t0 = t1
                set_step_state(task_id, tasks, 'subtitles', 'done')
            elif use_auto_captions and assemblyai_api_key:
                # Already transcribed above if enabled; use word timestamps
                if 'transcript' in locals() and transcript and getattr(transcript, 'words', None):
                    # Compute vertical relative y (0=top, 1=bottom). Slider is distance from bottom.
                    rel_y = 1.0 - max(0.0, min(1.0, position_vertical_percent))
                    if aspect_ratio == '16:9':
                        # Group words into sentences by punctuation or pauses
                        sentence_tokens = []
                        sentence_start = None
                        prev_end = None
                        punct_pat = re.compile(r"[\.!?;:]+$")
                        def flush_sentence(start_time, end_time, tokens):
                            if not tokens:
                                return
                            # Further chunk each sentence into ~5-8 word segments proportional to duration
                            total_words = len(tokens)
                            total_dur = max(0.01, end_time - start_time)
                            chunks = chunk_tokens(tokens)
                            acc = start_time
                            for chunk in chunks:
                                frac = len(chunk) / float(total_words)
                                ch_dur = max(0.05, total_dur * frac)
                                ch_start = acc
                                ch_end = ch_start + ch_dur
                                acc = ch_end
                                text = " ".join(chunk).strip()
                                overlay_clips.append(
                                    make_text_clip(text, ch_start, ch_end, final_clip, font, font_size, font_color, rel_y)
                                )
                        for w in transcript.words:
                            # AssemblyAI word times are ms
                            w_start = (w.start or 0) / 1000.0
                            w_end = (w.end or (w.start or 0)) / 1000.0
                            if w_end <= w_start:
                                w_end = w_start + 0.05
                            token = (w.text or '').strip()
                            if not token:
                                continue
                            if sentence_start is None:
                                sentence_start = w_start
                            # Break on long pause
                            if prev_end is not None and (w_start - prev_end) > CAPTION_PAUSE_BREAK_S and sentence_tokens:
                                flush_sentence(sentence_start, prev_end, sentence_tokens)
                                sentence_tokens = []
                                sentence_start = w_start
                            sentence_tokens.append(token)
                            prev_end = w_end
                            # Break on punctuation
                            if punct_pat.search(token):
                                flush_sentence(sentence_start, prev_end, sentence_tokens)
                                sentence_tokens = []
                                sentence_start = None
                                prev_end = None
                        # Flush any remaining tokens
                        if sentence_tokens and sentence_start is not None and prev_end is not None:
                            flush_sentence(sentence_start, prev_end, sentence_tokens)
                    else:
                        # Word-by-word for vertical formats
                        for w in transcript.words:
                            start = (w.start or 0) / 1000.0
                            end = (w.end or (w.start or 0)) / 1000.0
                            if end <= start:
                                end = start + 0.05
                            txt = (w.text or '').strip()
                            if not txt:
                                continue
                            overlay_clips.append(
                                make_text_clip(txt, start, end, final_clip, font, font_size, font_color, rel_y)
                            )
                set_step_state(task_id, tasks, 'subtitles', 'done')
            else:
                # No subtitles
                set_step_state(task_id, tasks, 'subtitles', 'done')
        except Exception as sub_e:
            # Fail gracefully on subtitle overlay generation
            set_step_state(task_id, tasks, 'subtitles', 'error')
            update_status(task_id, tasks, "processing", f"Subtitle overlay error: {sub_e}", progress=10)

        set_step_state(task_id, tasks, 'export', 'in_progress')
        update_status(task_id, tasks, "processing", "Compositing and exporting final video...", progress=10)
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
                    # Smoothly advance overall progress from 10% to 99% during export
                    try:
                        base = 10
                        span = 89  # 10 -> 99
                        tasks[task_id]['progress'] = min(99, base + int((pct / 100.0) * span))
                    except Exception:
                        pass
        export_logger = ExportLogger()
        tasks[task_id]['export_progress'] = 0

        # 1) Build main content (with overlays if any) strictly limited to narration duration
        if overlay_clips:
            main_clip = CompositeVideoClip([final_clip] + overlay_clips).set_duration(final_clip.duration)
        else:
            main_clip = final_clip

        # 2) Load closing Thankyou clip based on aspect ratio, set its audio to 50%, and add smooth transition
        try:
            if aspect_ratio == '16:9':
                thankyou_path = os.path.join('resource', 'Thankyou169.mp4')
            else:
                thankyou_path = os.path.join('resource', 'Thankyou 916.mp4')

            if os.path.exists(thankyou_path):
                ty_clip = VideoFileClip(thankyou_path)
                # Ensure sizes match composition; if not, resize to main clip size
                if ty_clip.w != main_clip.w or ty_clip.h != main_clip.h:
                    ty_clip = ty_clip.resize((main_clip.w, main_clip.h))
                # Thankyou clip audio at 50%
                if ty_clip.audio is not None:
                    ty_clip = ty_clip.volumex(0.5)
                # Subtle non-overlapping fades (0.3–0.5s), clamped to clip lengths
                try:
                    base_fd = float(transition_duration) if transition_duration else 0.5
                except Exception:
                    base_fd = 0.5
                fade_dur = max(0.3, min(0.5, base_fd))
                max_allowed = max(0.01, min(main_clip.duration, ty_clip.duration) / 2.0)
                fade_dur = min(fade_dur, max_allowed)
                main_faded = main_clip.fx(vfx.fadeout, fade_dur)
                ty_faded = ty_clip.fx(vfx.fadein, fade_dur)
                output_clip = concatenate_videoclips([main_faded, ty_faded], method='compose')
            else:
                # Fallback: no thankyou clip available, export main as-is
                output_clip = main_clip
        except Exception:
            # If anything fails around the thankyou clip, proceed with main content only
            output_clip = main_clip

        # 3) Export final video
        output_clip.write_videofile(output_path, codec='libx264', audio_codec='aac', fps=24, threads=4, logger=export_logger)

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
        # Remove uploaded temp files (direct uploads) and Drive temp dir if present
        try:
            for f in (config.get('temp_files') or []):
                if f and os.path.exists(f):
                    os.remove(f)
            temp_dir = config.get('temp_dir')
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as _cleanup_err:
            # best-effort cleanup; do not fail the task for cleanup issues
            pass
        # Also remove the original uploads if they are no longer needed
        # (Assuming they are in a temp location managed by the main app)
        set_step_state(task_id, tasks, 'cleanup', 'done')
