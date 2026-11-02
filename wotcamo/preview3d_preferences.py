"""Viewer-only preferences, kept separate from light recipes and game files."""
import json
from pathlib import Path
from .common import ROOT,write_json

PROFILES={'流畅':'fast','均衡':'balanced','高画质':'fine'}
PATH=ROOT/'config/preview3d.json'

def load(path=None):
    try:
        data=json.loads(Path(path or PATH).read_text(encoding='utf-8-sig'))
        return data['performance'] if data.get('performance') in PROFILES else '均衡'
    except (OSError,ValueError,TypeError,AttributeError):return '均衡'

def save(value,path=None):
    if value not in PROFILES:raise ValueError('性能档只支持流畅、均衡和高画质。')
    write_json(Path(path or PATH),dict(performance=value))
