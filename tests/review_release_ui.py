"""Open only this build's light editor for visual review; no game actions."""
from pathlib import Path
from wotcamo.light_gui import LightMaker
from wotcamo.common import ROOT
app=LightMaker();app.geometry('1320x950+60+30');app.auto_save.set(False)
app.title_value.set('我的灯效');app.direction.set('偏右下')
def position():
    app.update_idletasks();app.editor_viewport.yview_moveto(1)
app.after(500,position)
def check():
    if (ROOT/'.cache/close_review_ui').exists():app.destroy()
    else:app.after(300,check)
app.after(1000,check);app.after(120000,app.destroy);app.mainloop()
