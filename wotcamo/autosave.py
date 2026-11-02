"""Local recovery files; never overwrite a user's manual project."""
from pathlib import Path
from datetime import datetime
import json, uuid
from .common import ROOT, write_json

FOLDER = ROOT / '自动保存'
SETTINGS = ROOT / 'config/自动保存.json'
INTERVAL_MS = 300000

def enabled(kind):
    try:
        data = json.loads(SETTINGS.read_text(encoding='utf-8'))
        return data.get(kind, True) is True
    except (OSError, ValueError, TypeError, AttributeError):
        return True

def set_enabled(kind, value):
    try:
        data = json.loads(SETTINGS.read_text(encoding='utf-8'))
        if not isinstance(data, dict): data = {}
    except (OSError, ValueError): data = {}
    data[kind] = bool(value)
    write_json(SETTINGS, data)

def new_path(kind, extension, group=None):
    folder = FOLDER / kind
    if group:
        if not all(c in '0123456789abcdef' for c in group) or len(group) != 64:
            raise ValueError('工程标识无效')
        folder = folder / group
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + uuid.uuid4().hex[:8] + extension)

def prune(path, keep=3):
    files = sorted(path.parent.glob('*' + path.suffix), key=lambda p: p.name, reverse=True)
    for old in files[keep:]:
        try: old.unlink()
        except OSError: pass

def save_draft(data):
    path = new_path('涂装草稿', '.json')
    write_json(path, {'schema': 1, 'draft': data})
    prune(path)
    return path

def load_draft(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema') != 1 or not isinstance(value.get('draft'), dict):
        raise ValueError('不是有效的涂装草稿。')
    return value['draft']
