"""Explicit outer ZIP delivery; the installable .wotmod stays uncompressed."""
import hashlib,json,zipfile
from pathlib import Path
from .light_effects import digest

def bundle(target,report):
    target=Path(target)
    if digest(target)!=report['artifact']['sha256']:raise ValueError('安装包已改变，不能按旧验证记录打包。')
    destination=target.with_suffix('.zip')
    with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.write(target,target.name)
        for name in ('验证记录.json','使用说明.txt','配方.json'):
            file=target.parent/name
            if file.is_file():z.write(file,name)
    with zipfile.ZipFile(destination) as z:
        if z.testzip() is not None:raise ValueError('ZIP 校验失败。')
        with z.open(target.name) as file:
            if hashlib.file_digest(file,'sha256').hexdigest()!=report['artifact']['sha256']:raise ValueError('ZIP 中安装包的哈希不符。')
    result=dict(path=str(destination),sha256=digest(destination),game_archive_sha256=report['artifact']['sha256'],bytes=destination.stat().st_size,embedded_editable_project=report.get('embedded_project',{}).get('enabled',False))
    (target.parent/'自动打包记录.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
