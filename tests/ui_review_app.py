"""Open our own editor for visual QA; never opens or changes the game."""
from pathlib import Path
from wotcamo.light_gui import LightMaker
from wotcamo.common import ROOT
import sys
from wotcamo.ae_gui import AEImporter
from wotcamo.gui import Workbench
app=Workbench() if '--main' in sys.argv else AEImporter() if '--ae' in sys.argv else LightMaker()
app.geometry('1040x750+60+30' if '--main' in sys.argv else '1120x800+60+30' if '--ae' in sys.argv else '1320x960+60+30')
if hasattr(app,'auto_save'):app.auto_save.set(False)
if hasattr(app,'direction'):app.direction.set('偏右下')
if hasattr(app,'title_value'):app.title_value.set('界面检查')
if hasattr(app,'editor_viewport'):app.after(600,lambda:app.editor_viewport.yview_moveto(1))
if '--presets' in sys.argv:app.after(700,app.manage_presets)
def stop_when_requested():
    if (ROOT/'.cache/stop_ui_review').exists():app.destroy()
    else:app.after(500,stop_when_requested)
app.after(1000,stop_when_requested);app.after(120000,app.destroy);app.mainloop()
