"""Run actual Tk controls on a separate Windows desktop, never switching to it.

--program selects the shipped code; --tests selects its accompanying source.
Only UI output/cache paths are redirected to temporary storage. No game,
browser, installation action or input on the user's desktop is exercised.
"""
import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import tempfile
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--tests',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    program=args.program.resolve();source=args.tests.resolve()
    if not (program/'wotcamo').is_dir() or not (source/'tests/test_ui_bugfix33.py').is_file():
        parser.error('Program or regression tests are missing.')

    # CreateDesktop/SetThreadDesktop affect this test thread only. Never call
    # SwitchDesktop: the user's current desktop and foreground game stay put.
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.CreateDesktopW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
    user.CreateDesktopW.restype=wintypes.HANDLE
    user.SetThreadDesktop.argtypes=[wintypes.HANDLE];user.SetThreadDesktop.restype=wintypes.BOOL
    desktop=user.CreateDesktopW('WotUiCheck_'+uuid.uuid4().hex,None,None,0,0x01ff,None)
    if not desktop:raise ctypes.WinError(ctypes.get_last_error())
    if not user.SetThreadDesktop(desktop):raise ctypes.WinError(ctypes.get_last_error())

    sys.path[:0]=[str(program),str(source),str(source/'tests')]
    import unittest
    from unittest.mock import patch
    from wotcamo import ui_theme,gui,ae_gui,light_gui
    for module in (ui_theme,gui,ae_gui,light_gui):
        assert Path(module.__file__).resolve().is_relative_to(program)
    names=['tests.test_ui_bugfix33','tests.test_ui_consistency','tests.test_unified31',
           'tests.test_ae_gui','tests.test_light_responsive','tests.test_light_tooltips']
    # Synthetic error recovery and empty AE projects must not leave error logs
    # or caches in the delivered program, nor change the user's preferences.
    cache=source/'.cache';cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ui33_',dir=cache) as folder:
        scratch=Path(folder)
        with patch.object(tempfile,'tempdir',folder),patch.object(gui,'ROOT',scratch),patch.object(ae_gui,'ROOT',scratch),patch.object(light_gui,'ROOT',scratch),patch.object(ui_theme,'theme_preference',return_value=False):
            result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    print('TESTED_PROGRAM',program,flush=True)
    print('ISOLATED_UI_SUITE',result.testsRun,len(result.failures),len(result.errors),flush=True)
    return 0 if result.testsRun==33 and result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
