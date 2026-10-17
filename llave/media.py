"""Brand images (agent photo, agency logo): auto-rotate, strip all metadata, resize, save under MEDIA_DIR/brand/."""
import hashlib
import io
import os

from PIL import Image, ImageOps

from . import db


def save_brand_image(data, kind='avatar'):
    """kind 'avatar' -> 400x400 square JPEG; 'logo' -> max 600x200 PNG (keeps transparency). Returns path relative to MEDIA_DIR."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    except Exception:
        raise ValueError('No pudimos leer esa imagen. Usa JPG, PNG o WebP.')
    sha = hashlib.sha256(data).hexdigest()
    folder = os.path.join(db.MEDIA_DIR, 'brand')
    os.makedirs(folder, exist_ok=True)
    if kind == 'avatar':
        if min(img.size) < 200:
            raise ValueError('La foto es muy pequeña: mínimo 200 px.')
        img = ImageOps.fit(img.convert('RGB'), (400, 400), Image.LANCZOS)
        name = 'avatar-%s.jpg' % sha[:24]
        img.save(os.path.join(folder, name), 'JPEG', quality=85, optimize=True, progressive=True)
    else:
        img = img.convert('RGBA')
        img.thumbnail((600, 200), Image.LANCZOS)
        name = 'logo-%s.png' % sha[:24]
        img.save(os.path.join(folder, name), 'PNG', optimize=True)
    return 'brand/' + name
