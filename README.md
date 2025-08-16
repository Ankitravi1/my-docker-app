# Automated Social Video Generator

This project is a simple web application for generating short-form videos (9:16 aspect ratio) from a collection of images and an audio file. It automatically adds subtitles and a Ken Burns (pan and zoom) effect to the images.

## Features

-   Web-based interface for easy video creation.
-   Combines multiple images and an audio track.
-   Crops images to 9:16 aspect ratio.
-   Applies a subtle Ken Burns (zoom) effect.
-   Generates subtitles automatically from the audio using AssemblyAI.
-   Customizable subtitle font, color, and position.

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
```

## Setup and Installation

1.  **Clone the repository (or download the files).**

2.  **Install Python 3.11.**

3.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

4.  **Install dependencies:**
    Navigate to the project directory and run:
    ```bash
    pip install -r requirements.txt
    ```

5.  **Set up your API Key:**
    Open the `.env` file and add your AssemblyAI API key:
    ```
    ASSEMBLYAI_API_KEY=your_api_key_here
    ```

## How to Run

1.  Make sure you have completed the setup steps above.
2.  Run the Flask application:
    ```bash
    python main.py
    ```
3.  Open your web browser and navigate to `http://127.0.0.1:5000/`.

## Additional Setup and Dependencies

-  __FFmpeg__: MoviePy relies on FFmpeg for reading/writing media. It is usually bundled via `imageio-ffmpeg`, but if you encounter FFmpeg errors, install FFmpeg system-wide and ensure it is on your PATH.
   - Windows: https://www.gyan.dev/ffmpeg/builds/ (download, unzip, add `bin` to PATH)
   - macOS: `brew install ffmpeg`
   - Linux (Debian/Ubuntu): `sudo apt-get install ffmpeg`

-  __ImageMagick (Windows only, for TextClip captions)__:
   - Install ImageMagick 7 (Q16 HDRI) from https://imagemagick.org/script/download.php#windows
   - Update the binary path in `video_processor.py` if needed:
     - See lines near: `change_settings({"IMAGEMAGICK_BINARY": r"C:\\Program Files\\ImageMagick-7.1.2-Q16-HDRI\\magick.exe"})`
   - If you change install location or version, update that path accordingly.

## Environment Variables

-  __ASSEMBLYAI_API_KEY__: Needed only if you want to auto-generate captions.
   - Set in `.env` as: `ASSEMBLYAI_API_KEY=your_api_key_here`
   - If you do not wish to use auto captions, uncheck the "Auto-generate captions" box in the UI, or provide an `.srt` file to override.

Security note: never commit real API keys to version control. `.env` is intended to be local-only.

## API Endpoints

-  __GET `/`__
   - Renders `templates/index.html` — a web UI to submit jobs.

-  __POST `/generate`__
   - Multipart form fields:
     - `project_title` (string)
     - `audio` (file, required — `.mp3`)
     - `images` (file[], required — `.jpg/.jpeg/.png`, multiple allowed)
     - `srt` (file, optional — provide to override auto captions)
     - `font` (string, default `Arial`)
     - `font_color` (hex, default `#FFFFFF`)
     - `font_size` (int, default `48`)
     - `position_vertical` (0–100, distance from bottom; UI slider)
     - `caption_auto` (checkbox; when checked enables AssemblyAI transcription)
   - Response: `{ status: 'success', message, task_id }` on start

-  __GET `/status/<task_id>`__
   - Returns task status, progress, logs, step checklist, and export progress.

-  __GET `/download/<task_id>`__
   - Available once task status is `completed`. Returns the final `.mp4` for download.

## Outputs

- Videos are written to `outputs/<project-id>/<project-id>.mp4`.
- The `<project-id>` combines a sanitized `project_title` and a short task id (see `main.py`).

## Frontend Usage Tips

-  Images are auto-cropped to 9:16 and lightly zoomed (Ken Burns effect).
-  The vertical position slider controls how far from the bottom captions appear.
-  Provide an SRT to use your own timings/text; otherwise, enable auto captions with a valid AssemblyAI key.

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
-  Frontend: `templates/index.html` and `static/app.js` — form submission, polling `/status`, live logs, progress bars, and checklist UI.

## How to Use

1.  Fill in the project title.
2.  Upload an MP3 audio file.
3.  Upload one or more image files (JPG or PNG).
4.  Customize the subtitle options if desired.
5.  Click "Generate Video".
6.  Wait for the process to complete, and a download link will appear.
