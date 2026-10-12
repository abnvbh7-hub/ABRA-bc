import os
import mimetypes
from pathlib import Path
from typing import Optional, Tuple
import cv2
import numpy as np

# Cache directory configuration
BACKEND_DIR = Path(__file__).resolve().parent
CACHE_DIR = BACKEND_DIR / "cache"
IMAGES_DIR = CACHE_DIR / "images"
THUMBS_DIR = CACHE_DIR / "thumbs"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)
THUMBS_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_key(object_key: str) -> str:
    """Sanitizes an S3 object key into a safe filename."""
    return object_key.replace("/", "_").replace("\\", "_").replace("..", "_")


def guess_mime_type(file_path: Path, data: Optional[bytes] = None) -> str:
    """Guesses MIME type from file extension or content magic bytes."""
    if data:
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        elif data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
            return "image/gif"
        elif data.startswith(b"RIFF") and b"WEBP" in data[:16]:
            return "image/webp"
        elif b"ftyp" in data[4:12]:
            return "video/mp4"

    mime, _ = mimetypes.guess_type(str(file_path))
    return mime or "image/jpeg"


def get_cached_image_path(object_key: str) -> Optional[Path]:
    """Returns the cached full-resolution image path if it exists."""
    safe_name = sanitize_key(object_key)
    target = IMAGES_DIR / safe_name
    if target.is_file() and target.stat().st_size > 0:
        return target
    # Check with common extensions
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".mp4"]:
        ext_target = IMAGES_DIR / f"{safe_name}{ext}"
        if ext_target.is_file() and ext_target.stat().st_size > 0:
            return ext_target
    return None


def get_cached_thumb_path(object_key: str) -> Optional[Path]:
    """Returns the cached thumbnail image path if it exists."""
    safe_name = sanitize_key(object_key)
    target = THUMBS_DIR / f"{safe_name}.jpg"
    if target.is_file() and target.stat().st_size > 0:
        return target
    return None


def generate_thumbnail(image_bytes: bytes, max_dim: int = 540) -> Optional[bytes]:
    """Generates an optimized JPEG thumbnail using OpenCV."""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 82]
        success, buffer = cv2.imencode(".jpg", img, encode_param)
        if success:
            return buffer.tobytes()
    except Exception as e:
        print(f"[CacheManager] Thumbnail generation error: {e}")
    return None


def save_bytes_atomic(target_path: Path, data: bytes) -> None:
    """Writes bytes atomically using a temporary file to avoid partial reads."""
    temp_path = target_path.with_suffix(f"{target_path.suffix}.tmp_{os.getpid()}")
    try:
        with open(temp_path, "wb") as f:
            f.write(data)
        temp_path.replace(target_path)
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise e


def get_or_fetch_image_bytes(object_key: str, s3_client, bucket_name: str) -> Optional[Tuple[bytes, str]]:
    """
    Returns (image_bytes, mime_type).
    Checks local disk cache first. If absent, fetches from S3 and stores locally.
    """
    cached_path = get_cached_image_path(object_key)
    if cached_path:
        try:
            with open(cached_path, "rb") as f:
                data = f.read()
            mime = guess_mime_type(cached_path, data)
            return data, mime
        except Exception as e:
            print(f"[CacheManager] Read error for {cached_path}: {e}")

    # Fetch from S3
    try:
        print(f"[CacheManager] Cache miss for {object_key}, downloading from S3...")
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        data = response["Body"].read()
        mime = response.get("ContentType") or guess_mime_type(Path(object_key), data)

        safe_name = sanitize_key(object_key)
        target_path = IMAGES_DIR / safe_name
        save_bytes_atomic(target_path, data)
        print(f"[CacheManager] Successfully cached {object_key} ({len(data)} bytes).")

        # Also pre-generate thumbnail if it's an image
        if mime.startswith("image/"):
            thumb_bytes = generate_thumbnail(data)
            if thumb_bytes:
                thumb_path = THUMBS_DIR / f"{safe_name}.jpg"
                save_bytes_atomic(thumb_path, thumb_bytes)

        return data, mime
    except Exception as e:
        print(f"[CacheManager] S3 fetch error for {object_key}: {e}")
        return None


def get_image_file_path(object_key: str, s3_client, bucket_name: str, thumb: bool = False) -> Tuple[Optional[Path], str]:
    """
    Ensures the image is locally cached and returns (Path, mime_type).
    If thumb=True, returns the thumbnail path (generating it if needed).
    """
    safe_name = sanitize_key(object_key)

    if thumb:
        thumb_path = get_cached_thumb_path(object_key)
        if thumb_path:
            return thumb_path, "image/jpeg"

    # Check full image in cache
    full_path = get_cached_image_path(object_key)
    if full_path:
        if thumb:
            # Generate thumbnail from cached full image
            try:
                with open(full_path, "rb") as f:
                    data = f.read()
                thumb_bytes = generate_thumbnail(data)
                if thumb_bytes:
                    t_path = THUMBS_DIR / f"{safe_name}.jpg"
                    save_bytes_atomic(t_path, thumb_bytes)
                    return t_path, "image/jpeg"
            except Exception as e:
                print(f"[CacheManager] Failed to create thumb from cached full image: {e}")
        mime = guess_mime_type(full_path)
        return full_path, mime

    # Not in cache: fetch and save
    res = get_or_fetch_image_bytes(object_key, s3_client, bucket_name)
    if not res:
        return None, "application/octet-stream"
    data, mime = res

    if thumb and mime.startswith("image/"):
        thumb_path = get_cached_thumb_path(object_key)
        if thumb_path:
            return thumb_path, "image/jpeg"

    full_path = get_cached_image_path(object_key)
    return full_path, mime
