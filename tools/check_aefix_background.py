"""Run only non-window regressions, with an explicit Tk creation guard."""
import ctypes
import sys
import tempfile
import tkinter as tk
import unittest
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.SetPriorityClass.restype=wintypes.BOOL
    assert kernel.SetPriorityClass(wintypes.HANDLE(-1),0x40)
    root=Path(__file__).resolve().parents[1];tempfile.tempdir=str(root/'.cache/test_tmp')
    names=['tests.test_glass32','tests.test_ae_mirrorfix','tests.test_ae_review_fixes','tests.test_ae_preset_notes','tests.test_ae_color','tests.test_ae_sides',
           'tests.test_ae_surface','tests.test_ae_effects','tests.test_ae_deform','tests.test_ae_presets.AEPresetTests']
    with (root/'.cache/aefix_tests.log').open('w',encoding='utf-8') as log:
        with patch.object(tk.Tk,'__init__',side_effect=AssertionError('Window creation forbidden during background checks')),\
             patch.object(tk.Toplevel,'__init__',side_effect=AssertionError('Window creation forbidden during background checks')):
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    print('GUARDED_BACKGROUND_TESTS',result.testsRun,len(result.failures),len(result.errors),flush=True)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
