"""Run Tk checks on a separate non-visible Windows desktop, never SwitchDesktop."""
import argparse,ctypes,sys,uuid
from ctypes import wintypes
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--program',type=Path,required=True);p.add_argument('--tests',type=Path)
    args=p.parse_args();program=args.program.resolve();tests=(args.tests or program).resolve()
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.CreateDesktopW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
    user.CreateDesktopW.restype=wintypes.HANDLE;user.SetThreadDesktop.argtypes=[wintypes.HANDLE];user.SetThreadDesktop.restype=wintypes.BOOL
    desktop=user.CreateDesktopW('LocalSkinFilter_'+uuid.uuid4().hex,None,None,0,0x1ff,None)
    if not desktop or not user.SetThreadDesktop(desktop):raise ctypes.WinError(ctypes.get_last_error())
    sys.path[:0]=[str(program),str(tests)]
    import unittest,filter_gui
    assert Path(filter_gui.__file__).resolve().is_relative_to(program)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('test_filter_gui'))
    print('FILTER_UI',result.testsRun,len(result.failures),len(result.errors))
    return 0 if result.testsRun==5 and result.wasSuccessful()else 1


if __name__=='__main__':raise SystemExit(main())
