"""GUI entry for the standalone portable app."""
import sys
import traceback
from pathlib import Path


def main():
    root=Path(__file__).resolve().parent
    try:
        (root/'.cache').mkdir(exist_ok=True)
        log=(root/'.cache/界面错误.log').open('a',encoding='utf-8')
        sys.stderr=log
    except OSError:log=None
    try:
        from converter_gui import App
        App().mainloop()
    except Exception as error:
        traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror('转换器无法启动',str(error)+'\n请保留完整解压目录；详细信息位于 .cache/界面错误.log。')
        except Exception:pass
        raise SystemExit(1)
    finally:
        if log:log.close()


if __name__=='__main__':main()
