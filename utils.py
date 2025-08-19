# Utility functions can be added here later.

import os
import zipfile
from typing import List, Tuple, Optional
from PIL import Image

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def download_drive_folder(folder_url: str, dest_dir: str) -> str:
    """
    Download a shared Google Drive folder into dest_dir using gdown.
    The link must be accessible to Anyone with the link (Viewer).
    Returns the directory where files were downloaded.
    """
    ensure_dir(dest_dir)
    try:
        import gdown
    except ImportError as e:
        raise RuntimeError("gdown is required to download from Google Drive. Please install it.") from e

    # gdown will create subdirectories under dest_dir as needed
    gdown.download_folder(url=folder_url, output=dest_dir, quiet=False, use_cookies=False)
    return dest_dir

def extract_zip_files_in_dir(root_dir: str):
    for root, _, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith('.zip'):
                zip_path = os.path.join(root, f)
                try:
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        zf.extractall(root)
                except Exception:
                    # Ignore bad zips; continue
                    pass

def collect_assets(root_dir: str) -> Tuple[Optional[str], List[str]]:
    """
    Collect audio (.mp3) and images (.jpg/.jpeg/.png) recursively from root_dir.
    If multiple mp3s exist, pick the largest by file size.
    Returns (audio_path, image_paths)
    """
    images: List[str] = []
    audios: List[str] = []
    for r, _, files in os.walk(root_dir):
        for f in files:
            lf = f.lower()
            full = os.path.join(r, f)
            if lf.endswith('.mp3'):
                audios.append(full)
            elif lf.endswith('.jpg') or lf.endswith('.jpeg') or lf.endswith('.png') or lf.endswith('.webp'):
                images.append(full)
            else:
                # Handle files without extensions: try to open as image
                try:
                    with Image.open(full) as im:
                        im.verify()  # quick check
                    images.append(full)
                except Exception:
                    pass

    # pick largest mp3 if any
    audio_path: Optional[str] = None
    if audios:
        audio_path = max(audios, key=lambda p: os.path.getsize(p) if os.path.exists(p) else -1)

    # sort images by name for stable ordering
    images.sort()
    return audio_path, images