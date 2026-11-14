"""Check a user-selected output folder before processing a batch."""
import uuid
from pathlib import Path


def check_output_directory(output,client_root):
    root=Path(output).expanduser().resolve()
    client=Path(client_root).expanduser().resolve()
    if not root.is_dir():raise ValueError('所选输出目录不存在，请重新选择。')
    if root.is_relative_to(client):raise ValueError('请选择游戏目录以外的输出文件夹。')
    probe=root/('.wot_write_test_'+uuid.uuid4().hex+'.tmp')
    created=False
    try:
        with probe.open('xb') as stream:
            created=True;stream.write(b'output directory check')
    except PermissionError as error:
        raise PermissionError('无法在所选输出目录创建文件：%s。请改选当前账户可写的文件夹，例如“文档”或“桌面”。系统信息：%s'%(root,error)) from error
    finally:
        if created:
            try:probe.unlink()
            except OSError as error:
                raise OSError('输出目录检查文件无法清理：%s（%s）'%(probe,error)) from error
    return root
