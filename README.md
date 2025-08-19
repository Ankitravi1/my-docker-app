# Automated Social Video Generator

This project is a simple web application for generating short-form videos (9:16 or 16:9) from a collection of images and an audio file. It automatically adds subtitles and a Ken Burns (pan and zoom) effect to the images.

## Features

-   Web-based interface for easy video creation.
-   Combines multiple images and an audio track.
-   Crops images to 9:16 or 16:9 aspect ratio.
-   Applies a subtle Ken Burns (zoom) effect.
-   Generates subtitles automatically from the audio using AssemblyAI.
-   Customizable subtitle font, color, and position.
-   Google Drive folder ingestion (recommended) with numbered files supported.
-  Frontend shows an elapsed timer and a weighted progress bar (no checklist or logs in UI).
-   Optional background music with on/off toggle and selectable level.
-   Captions behavior by aspect ratio:
    - 16:9 uses short caption chunks (~5–8 words) with a larger font (size 60) positioned at 20% from bottom.
    - 9:16 uses word-by-word captions with user-selected font size and vertical position.

## Testing Link
- 916 - https://drive.google.com/drive/folders/1FQt68G9JsyTs4ADF0mQV79T8Pf2MLEuQ?usp=sharing
- 169 - https://drive.google.com/drive/folders/1XUOA47QbbRvVUxsJOBtoJNlQ-PxX8dyo?usp=sharing

## Project Structure

```
/video_generator
|-- main.py               # The main Flask application
|-- video_processor.py    # Core video generation logic
|-- utils.py              # Utility functions
|-- requirements.txt      # Python dependencies
|-- .env                  # For API keys and environment variables
|-- /templates
|   |-- index.html        # Frontend HTML
|-- /static
|   |-- app.js            # Frontend JavaScript
|-- /uploads              # Temporary storage for uploaded files
|-- /outputs              # Final videos are saved here
|-- /resource             # Default background music
    |-- Pulsar.mp3        # Default background music file
```

## Step 1 — Install prerequisites

-  __FFmpeg (required)__
   - Ubuntu: `sudo apt-get update && sudo apt-get install -y ffmpeg`
   - macOS: `brew install ffmpeg`
   - Windows: Download from https://www.gyan.dev/ffmpeg/builds/ (unzip and add the `bin` folder to your PATH)

-  __ImageMagick (used by MoviePy TextClip for captions)__
   - Ubuntu: `sudo apt-get install -y imagemagick`
   - macOS: `brew install imagemagick`
   - Windows: Install ImageMagick 7 (Q16 HDRI) from https://imagemagick.org/script/download.php#windows
     - After install, set environment variable `IMAGEMAGICK_BINARY` to the full path of `magick.exe` (e.g., `C:\\Program Files\\ImageMagick-7.1.2-Q16-HDRI\\magick.exe`).
     - The code in `video_processor.py` reads this env var and has a common default, but setting it explicitly is recommended.

-  __PATH notes__
   - Linux/macOS typically need no extra config; `ffmpeg` and `magick` are found on PATH.
   - On Windows, ensure FFmpeg's `bin` is on PATH and `IMAGEMAGICK_BINARY` is set if MoviePy cannot find ImageMagick automatically.

### Ubuntu quick start

```bash
# System deps
sudo apt-get update && sudo apt-get install -y ffmpeg imagemagick

# Python env
python3 -m venv venv
source venv/bin/activate

# Python packages
pip install -r requirements.txt

# (Optional) captions via AssemblyAI
export ASSEMBLYAI_API_KEY="your_api_key_here"

# Run the app
python main.py
```

## Step 2 — Create Python environment and install packages

1.  **Clone the repository (or download the files).**

2.  **Install Python 3.10+**

3.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `source .venv\Scripts\activate`
    ```

4.  **Install dependencies:**
    Navigate to the project directory and run:
    ```bash
    pip install -r requirements.txt
    ```

5.  (Optional) **Set up your API Key:**
    Open the `.env` file and add your AssemblyAI API key:
    ```
    ASSEMBLYAI_API_KEY=your_api_key_here
    ```

## Step 3 — Configure environment variables

-  __ASSEMBLYAI_API_KEY__ (optional, for auto captions). See details in the "Environment Variables" section below.
-  __IMAGEMAGICK_BINARY__ (Windows only) — set to full path of `magick.exe` if MoviePy cannot find it automatically.

## Step 4 — Run the app

1.  Make sure you have completed the setup steps above.
2.  Run the Flask application:
    ```bash
    python main.py
    ```
3.  Open your web browser and navigate to `http://127.0.0.1:5000/`.

 

## Environment Variables

-  __ASSEMBLYAI_API_KEY__: Needed only if you want to auto-generate captions.
   - Set in `.env` as: `ASSEMBLYAI_API_KEY=your_api_key_here`
   - If you do not wish to use auto captions, uncheck the "Auto-generate captions" box in the UI, or provide an `.srt` file to override.

-  __IMAGEMAGICK_BINARY__ (Windows): Absolute path to `magick.exe` used by MoviePy `TextClip`.
-  __BGM_PATH__: Optional override for the background music track path. Defaults to `resource/Pulsar.mp3`.
-  __PORT__ (optional): If you run behind a different port/proxy, configure Flask accordingly.

Security note: never commit real API keys to version control. `.env` is intended to be local-only.

## API Endpoints

-  __GET `/`__
   - Renders `templates/index.html` — a web UI to submit jobs.

-  __POST `/generate`__
   - Multipart form fields:
     - `project_title` (string)
     - `drive_link` (string, optional — preferred. Public Google Drive folder URL)
     - `audio` (file, optional fallback — `.mp3`)
     - `images` (file[], optional fallback — `.jpg/.jpeg/.png/.webp`, multiple allowed)
     - `srt` (file, optional — provide to override auto captions)
     - `aspect_ratio` (string, `9:16` or `16:9`, default `9:16`)
     - `font` (string, default `Arial`)
     - `font_color` (hex, default `#FFFFFF`)
     - `font_size` (int, default `48`; forced to `60` for `16:9`)
     - `position_vertical` (0–100, distance from bottom; UI slider; ignored for `16:9` which is fixed at 20%)
     - `caption_auto` (checkbox; when checked enables AssemblyAI transcription — enabled by default in UI)
     - `background_music` (checkbox; default on. When unchecked, disables background music)
     - `background_music_level` (int; one of `4,6,8,10,12` — controls background music loudness percent)
   - Response: `{ status: 'success', message, task_id }` on start

-  __GET `/status/<task_id>`__
   - Returns task status, progress, logs, step checklist, and export progress.

-  __GET `/download/<task_id>`__
   - Available once task status is `completed`. Returns the final `.mp4` for download with proper `Content-Disposition` and `Content-Length`.
   - Implementation detail: conditional responses are disabled and cache is set to no-store to ensure first-click reliability (avoid 206 Partial Content on initial download).

## Outputs

- Videos are written to `outputs/<project-id>/<project-id>.mp4`.
- The `<project-id>` combines a sanitized `project_title` and a short task id (see `main.py`).

## Frontend Usage Tips

-  Images are auto-cropped to 9:16 or 16:9 and lightly zoomed (Ken Burns effect).
-  The vertical position slider controls how far from the bottom captions appear.
-  Provide an SRT to use your own timings/text; otherwise, enable auto captions with a valid AssemblyAI key.
-  Auto captions are enabled by default in the UI. If no API key is set, captions will be skipped.
-  The progress bar reflects overall weighted progress; export dominates (~90% of total). An elapsed timer shows total job time.
-  Background music: toggle on/off and choose a level (4–12). Default is on at level 4. You can also override the track via `BGM_PATH`.
-  16:9 specifics: captions are chunked to ~5–8 words per overlay; font size is fixed to 60; caption vertical position is fixed to 20% from the bottom.
-  9:16 specifics: captions are word-by-word and fully controlled by your font size and vertical position inputs.

## Troubleshooting

-  __TextClip/ImageMagick errors on Windows__
   - Ensure ImageMagick is installed and `video_processor.py` points to the correct `magick.exe`.

-  __FFmpeg not found / export failures__
   - Install FFmpeg system-wide and ensure it's on PATH. Try again.

-  __AssemblyAI errors or timeouts__
   - Verify `ASSEMBLYAI_API_KEY` and network connectivity. You can proceed without captions by unchecking auto captions or using an SRT.

-  __Long processing times__
   - Use fewer/lower-resolution images, or a shorter audio track. Export progress is displayed separately from overall progress.

## Development Notes

-  Core logic: `video_processor.py` — crop to 9:16, Ken Burns, optional per-word caption overlays, export.
-  Flask app: `main.py` — endpoints, background worker thread, task state, safe file handling and download route.
-  Frontend: `templates/index.html` and `static/app.js` — form submission, polling `/status`, elapsed timer, and a single progress bar. Logs and checklist are no longer displayed.

## Step 5 — Use the app

1.  Fill in the project title.
2.  Paste a public Google Drive folder link (recommended). Alternatively, upload an MP3 and images.
3.  Optionally upload one `.mp3` and one or more image files (JPG/PNG/WEBP) if not using a Drive link.
4.  Choose the aspect ratio and customize caption options.
5.  (Optional) Configure background music: toggle on/off and select level.
6.  Click "Generate Video".
7.  When complete, click "Download Video". A download progress bar will show while saving.
