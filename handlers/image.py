"""
image.py — Fetch poster from URL and resize to 1280x720 (16:9).
Returns BytesIO ready to send as Telegram photo.
"""
import httpx
from PIL import Image
from io import BytesIO

TARGET_W = 1280
TARGET_H = 720


async def fetch_and_resize(url: str) -> BytesIO | None:
    """
    Download image from URL, resize + crop to 1280x720 (16:9).
    Returns BytesIO on success, None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw = resp.content

        img = Image.open(BytesIO(raw)).convert("RGB")

        # Scale to cover 1280x720 keeping aspect ratio, then center-crop
        img_ratio    = img.width / img.height
        target_ratio = TARGET_W / TARGET_H

        if img_ratio > target_ratio:
            # Wider than 16:9 — fit height, crop width
            new_h = TARGET_H
            new_w = int(img.width * TARGET_H / img.height)
        else:
            # Taller than 16:9 — fit width, crop height
            new_w = TARGET_W
            new_h = int(img.height * TARGET_W / img.width)

        img = img.resize((new_w, new_h), Image.LANCZOS)

        # Center crop to exactly 1280x720
        left = (new_w - TARGET_W) // 2
        top  = (new_h - TARGET_H) // 2
        img  = img.crop((left, top, left + TARGET_W, top + TARGET_H))

        output = BytesIO()
        img.save(output, format="JPEG", quality=90)
        output.seek(0)
        output.name = "poster.jpg"
        return output

    except Exception as e:
        return None  # fallback to original URL in caller
