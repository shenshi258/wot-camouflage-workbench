"""Shared native widget theme and reversible busy-state handling.

Use clam's own border elements instead of stretching transparent bitmap corners.
All desktop windows use the same state colours, font sizes and keyboard focus.
"""
import tkinter as tk
from tkinter import ttk
import json
from pathlib import Path
import weakref

BG='#f5f5f7'
CARD='#ffffff'
INK='#1d1d1f'
MUTED='#64748b'
ACCENT='#007aff'
BORDER='#dfe5ed'
FONT=('Microsoft YaHei UI',10)

def theme_preference():
    """A missing or unreadable preference always keeps the familiar theme."""
    from .common import ROOT
    try:
        return json.loads((ROOT/'config/ui_theme.json').read_text(encoding='utf-8')).get('glass') is True
    except (OSError,ValueError,AttributeError):
        return False

def save_theme_preference(glass):
    from .common import ROOT,write_json
    write_json(ROOT/'config/ui_theme.json',{'glass':bool(glass)})

def palette(glass):
    """Shared colours for classic Tk widgets; preserve image and colour swatches."""
    return dict(card='#f1f9ff' if glass else CARD,
                field='#f8fcff' if glass else '#ffffff',
                border='#b8d9ea' if glass else BORDER,
                nav='#d9edf8' if glass else '#edf2f8',
                selected='#c9e9fa' if glass else '#dcecff')

def apply_widget_theme(widget,role,glass):
    colors=palette(glass)
    if role=='surface':options=dict(bg=colors['card'])
    elif role=='nav':options=dict(bg=colors['nav'])
    elif role=='field':options=dict(bg=colors['field'],fg=INK,highlightbackground=colors['border'],highlightcolor=ACCENT)
    elif role=='list':options=dict(bg=colors['field'],fg=INK,selectbackground=colors['selected'],selectforeground='#075d94',
                                   relief='flat',highlightthickness=1,highlightbackground=colors['border'],highlightcolor=ACCENT,font=FONT)
    elif role=='menu':options=dict(bg=colors['field'],fg=INK,activebackground=colors['selected'],activeforeground='#075d94',disabledforeground=MUTED)
    else:raise ValueError('未知界面元素类型：'+str(role))
    widget.configure(**options)

def register_widget(widget,role):
    """Opt in only interface chrome; never recolour user-selected artwork."""
    app=widget._root()
    if not hasattr(app,'_theme_widgets'):app._theme_widgets=[]
    app._theme_widgets.append((weakref.ref(widget),role))
    apply_widget_theme(widget,role,theme_preference())
    return widget

def refresh_registered_widgets(app,glass):
    live=[]
    for ref,role in getattr(app,'_theme_widgets',[]):
        widget=ref()
        try:
            if widget is not None and widget.winfo_exists():
                apply_widget_theme(widget,role,glass);live.append((ref,role))
        except tk.TclError:pass
    app._theme_widgets=live

def refresh_combobox_popdowns(app,glass):
    """The Tcl-owned choice list does not inherit ttk styles after creation."""
    colors=palette(glass)
    def walk(parent):
        for child in getattr(parent,'winfo_children',lambda:[])():
            if isinstance(child,ttk.Combobox):
                path=str(child.tk.call('ttk::combobox::PopdownWindow',child))+'.f.l'
                if child.tk.call('winfo','exists',path):
                    child.tk.call(path,'configure','-background',colors['field'],'-foreground',INK,
                                  '-selectbackground',colors['selected'],'-selectforeground','#075d94')
            walk(child)
    walk(app)

def configure_notebook_tabs(style,glass=False):
    """Keep tab states legible and aligned with the active window palette.

    Clam draws a separate border/highlight around each tab. Set all three
    colours as well as the fill, otherwise its default grey bevel remains
    visible on the blue glass-style panels. Selected comes before active so
    moving the pointer over the current page never hides its selected state.
    """
    if glass:
        normal,hover,selected='#e5f4fc','#d7edf9','#c9e9fa'
        border,selected_border='#b8d9ea','#86bddb'
        foreground,selected_foreground='#31536b','#075d94'
    else:
        normal,hover,selected='#f2f6fb','#e6f1fc','#dcecff'
        border,selected_border='#d4e0ed','#a5caee'
        foreground,selected_foreground='#344e67','#075db3'
    style.configure('TNotebook.Tab',padding=(13,7),background=normal,foreground=foreground,
                    borderwidth=1,relief='solid',bordercolor=border,lightcolor=border,darkcolor=border)
    style.map('TNotebook.Tab',
              background=[('selected',selected),('active',hover)],
              foreground=[('disabled','#7a8997'),('selected',selected_foreground)],
              bordercolor=[('selected',selected_border)],
              lightcolor=[('selected',selected_border)],darkcolor=[('selected',selected_border)])

def configure_theme(app):
    glass=theme_preference()
    app.configure(background=BG)
    style=ttk.Style(app);style.theme_use('clam')
    style.configure('.',font=('Microsoft YaHei UI',10),background=BG,foreground=INK)
    for name,color in [('TFrame',CARD),('Card.TFrame',CARD),('Header.TFrame',CARD),('Backdrop.TFrame',BG)]:style.configure(name,background=color)
    style.configure('TLabel',background=CARD,foreground=INK)
    style.configure('Muted.TLabel',background=CARD,foreground=MUTED)
    style.configure('Canvas.TLabel',background=BG,foreground=MUTED)
    style.configure('Section.TLabel',background=CARD,font=('Microsoft YaHei UI',11,'bold'))
    style.configure('Header.TLabel',background=CARD,font=('Microsoft YaHei UI',18,'bold'))
    style.configure('Brand.TLabel',background=CARD,font=('Microsoft YaHei UI',16,'bold'))
    style.configure('PageTitle.TLabel',background=CARD,font=('Microsoft YaHei UI',16,'bold'))
    style.configure('PageSubtitle.TLabel',background=CARD,foreground=MUTED,font=('Microsoft YaHei UI',9))
    style.configure('Field.TLabel',background=CARD,foreground=MUTED,font=('Microsoft YaHei UI',9))
    style.configure('HeaderSub.TLabel',background=CARD,foreground=MUTED)
    style.configure('Panel.TFrame',background=CARD,bordercolor='#dfe5ed',borderwidth=1,relief='solid')
    style.configure('TLabelframe',background=CARD,bordercolor='#dfe5ed',borderwidth=1,relief='solid')
    style.configure('TLabelframe.Label',background=CARD,foreground=INK,font=('Microsoft YaHei UI',10,'bold'))
    style.configure('Badge.TLabel',background='#edf4ff',foreground='#2662a8',padding=(10,4))
    # Disabled is first: hovering an unavailable action must not suggest it works.
    style.configure('TButton',padding=(12,7),background='#f4f7fb',foreground=INK,bordercolor='#d8e0ea',lightcolor='#f4f7fb',darkcolor='#f4f7fb',borderwidth=1,focuscolor=ACCENT)
    style.map('TButton',background=[('disabled','#f0f3f7'),('pressed','#dbe8f9'),('active','#e8f1ff')],foreground=[('disabled','#68768a')],bordercolor=[('focus',ACCENT)])
    style.configure('Accent.TButton',padding=(13,7),background=ACCENT,foreground='white',lightcolor=ACCENT,darkcolor=ACCENT,bordercolor=ACCENT,font=('Microsoft YaHei UI',10,'bold'))
    style.map('Accent.TButton',background=[('disabled','#e7edf5'),('pressed','#005ac1'),('active','#086be0')],foreground=[('disabled','#607188'),('!disabled','white')],bordercolor=[('disabled','#d3dce9'),('focus','#004b9c'),('!disabled',ACCENT)],lightcolor=[('disabled','#e7edf5')],darkcolor=[('disabled','#e7edf5')])
    style.configure('TEntry',padding=6,fieldbackground=CARD,bordercolor='#d8e0ea',lightcolor=CARD,darkcolor=CARD)
    style.map('TEntry',bordercolor=[('focus',ACCENT)],fieldbackground=[('disabled','#f0f3f7'),('readonly','#f5f7fa')],foreground=[('disabled','#68768a')])
    style.configure('TCombobox',padding=5,fieldbackground=CARD,background='#f4f7fb',bordercolor='#d8e0ea',arrowsize=12)
    style.map('TCombobox',fieldbackground=[('disabled','#f0f3f7'),('readonly',CARD)],foreground=[('disabled','#68768a')],selectbackground=[('readonly',CARD)],selectforeground=[('readonly',INK)],bordercolor=[('focus',ACCENT)])
    style.configure('TCheckbutton',background=CARD,padding=(0,3))
    style.map('TCheckbutton',background=[('active',CARD)],foreground=[('disabled','#68768a')])
    style.configure('Scope.TRadiobutton',background='#f0f4fa',padding=(9,6),anchor='center')
    style.map('Scope.TRadiobutton',background=[('selected','#dcecff'),('active','#e8f1ff')],foreground=[('disabled','#68768a'),('selected','#005abf')])
    style.configure('Treeview',background=CARD,fieldbackground=CARD,foreground=INK,borderwidth=0,rowheight=30)
    style.configure('Treeview.Heading',background='#f4f7fb',foreground=MUTED,font=('Microsoft YaHei UI',9,'bold'),padding=(6,7),relief='flat')
    style.map('Treeview',background=[('selected','#dcecff')],foreground=[('selected','#005abf')])
    style.configure('TNotebook',background=CARD,borderwidth=0,tabmargins=0)
    configure_notebook_tabs(style)
    style.configure('Horizontal.TProgressbar',background=ACCENT,troughcolor='#e7edf5',borderwidth=0,thickness=5)
    style.configure('TPanedwindow',background=BG)
    # Clam's unconfigured menu/radio/scroll widgets otherwise retain a second
    # grey palette, even when their neighbouring buttons already use this theme.
    style.configure('TMenubutton',padding=(12,7),background='#f4f7fb',foreground=INK,bordercolor=BORDER)
    style.map('TMenubutton',background=[('disabled','#f0f3f7'),('active','#e8f1ff')],foreground=[('disabled',MUTED)])
    style.configure('TRadiobutton',background=CARD,foreground=INK,padding=(0,3))
    style.map('TRadiobutton',background=[('active',CARD)],foreground=[('disabled',MUTED)])
    for orient in ('Horizontal','Vertical'):
        style.configure(orient+'.TScrollbar',background='#d3dfed',troughcolor='#f4f7fb',borderwidth=0,arrowsize=12)
        style.map(orient+'.TScrollbar',background=[('active','#a9c7ed')])
    colors=palette(glass)
    for name,value in [('font',FONT),('background',colors['field']),('foreground',INK),('selectBackground',colors['selected']),('selectForeground','#075d94')]:app.option_add('*TCombobox*Listbox.'+name,value)
    if glass:
        # Tk does not support a real backdrop blur: use a restrained glass-like
        # blue palette while keeping text and controls opaque and legible.
        for name in ('TFrame','Card.TFrame','Header.TFrame','TLabel','Muted.TLabel','Section.TLabel','Header.TLabel','Brand.TLabel','PageTitle.TLabel','PageSubtitle.TLabel','Field.TLabel','HeaderSub.TLabel','TLabelframe','TLabelframe.Label','TCheckbutton','TRadiobutton','TNotebook'):
            style.configure(name,background='#f1f9ff')
        for name in ('Backdrop.TFrame','TPanedwindow'):style.configure(name,background='#dbeefa')
        style.configure('Panel.TFrame',background='#f1f9ff',bordercolor='#a9d2e9')
        style.configure('TLabelframe',bordercolor='#b8d9ea')
        style.configure('TButton',background='#e0f3fc',lightcolor='#f5fcff',darkcolor='#c7e3f2',bordercolor='#a8d1e5')
        style.map('TButton',background=[('disabled','#e8f1f6'),('pressed','#c7e4f4'),('active','#d3edf9')],foreground=[('disabled','#68768a')],bordercolor=[('focus',ACCENT)])
        style.configure('TEntry',fieldbackground='#f8fcff',bordercolor='#b8d9ea',lightcolor='#f8fcff',darkcolor='#f8fcff')
        style.map('TEntry',bordercolor=[('focus',ACCENT)],fieldbackground=[('disabled','#eaf2f6'),('readonly','#f2f9fc')],foreground=[('disabled','#68768a')])
        style.configure('TCombobox',fieldbackground='#f8fcff',background='#e0f3fc',bordercolor='#b8d9ea')
        style.map('TCombobox',fieldbackground=[('disabled','#eaf2f6'),('readonly','#f8fcff')],foreground=[('disabled','#68768a')],selectbackground=[('readonly','#f8fcff')],selectforeground=[('readonly',INK)],bordercolor=[('focus',ACCENT)])
        for name in ('TCheckbutton','TRadiobutton'):style.map(name,background=[('active','#f1f9ff')],foreground=[('disabled','#68768a')])
        style.configure('Scope.TRadiobutton',background='#e5f4fc')
        style.map('Scope.TRadiobutton',background=[('selected','#c9e9fa'),('active','#d7edf9')],foreground=[('disabled','#68768a'),('selected','#075d94')])
        style.configure('Treeview',background='#f8fcff',fieldbackground='#f8fcff')
        style.configure('Treeview.Heading',background='#e5f4fc')
        style.map('Treeview',background=[('selected','#c9e9fa')],foreground=[('selected','#075d94')])
        style.configure('TMenubutton',background='#e0f3fc',bordercolor='#a8d1e5')
        style.map('TMenubutton',background=[('disabled','#e8f1f6'),('active','#d3edf9')],foreground=[('disabled',MUTED)])
        for orient in ('Horizontal','Vertical'):
            style.configure(orient+'.TScrollbar',background='#b8d9ea',troughcolor='#e5f4fc')
            style.map(orient+'.TScrollbar',background=[('active','#86bddb')])
        style.configure('Badge.TLabel',background='#d5effb',foreground='#17658f')
        configure_notebook_tabs(style,glass=True)
        app.configure(background='#dbeefa')
    refresh_registered_widgets(app,glass)
    refresh_combobox_popdowns(app,glass)
    return style


def build_header(parent,subtitle='',textvariable=None):
    """One brand/header hierarchy for all editors; reserve action space first.

    Returning an action container lets each editor retain its own commands,
    while long explanatory text wraps into the remaining width at high DPI.
    """
    from . import APP_NAME,__version__
    app=parent.winfo_toplevel()
    header=ttk.Frame(parent,style='Header.TFrame',padding=(16,10))
    header.actions=ttk.Frame(header,style='Header.TFrame');header.actions.pack(side='right',padx=(12,0))
    theme_button=ttk.Button(header.actions)
    def refresh_theme(event=None):
        selected=theme_preference()
        if getattr(app,'_glass_preference',None)!=selected:
            configure_theme(app);app._glass_preference=selected
        theme_button.configure(text='界面：液态玻璃' if selected else '界面：经典')
        if hasattr(header,'logo'):header.logo.configure(bg='#f1f9ff' if selected else CARD)
    def toggle_theme():
        from tkinter import messagebox
        try:save_theme_preference(not theme_preference())
        except OSError as error:
            messagebox.showerror('界面风格','保存失败：'+str(error),parent=app);return
        refresh_theme()
    theme_button.configure(command=toggle_theme)
    theme_button.pack(side='right',padx=(8,0))
    refresh_theme()
    app._sync_theme=refresh_theme
    app.bind('<FocusIn>',refresh_theme,add='+')
    ttk.Label(header,text='本地创作 · '+__version__,style='Badge.TLabel').pack(side='right',padx=(12,0))
    logo=tk.Canvas(header,width=42,height=42,bg=CARD,highlightthickness=0);logo.pack(side='left',padx=(0,12))
    header.logo=logo
    refresh_theme()
    for radius,color in ((20,'#edf4ff'),(13,'#b4d8ff'),(6,ACCENT)):
        logo.create_oval(21-radius,21-radius,21+radius,21+radius,fill=color,outline='')
    title=ttk.Frame(header,style='Header.TFrame');title.pack(side='left',fill='x',expand=True)
    header.brand=ttk.Label(title,text=APP_NAME,style='Brand.TLabel');header.brand.pack(anchor='w')
    options=dict(textvariable=textvariable) if textvariable is not None else dict(text=subtitle)
    header.subtitle=ttk.Label(title,style='HeaderSub.TLabel',**options);header.subtitle.pack(anchor='w',pady=(3,0))
    header.bind('<Configure>',lambda event:header.subtitle.configure(wraplength=max(220,event.width-header.actions.winfo_reqwidth()-240)))
    return header


def prepare_dialog(dialog,section):
    """Apply the parent editor's palette without replacing native file dialogs."""
    from . import APP_NAME
    dialog.title(APP_NAME+' · '+section);dialog.configure(background='#dbeefa' if theme_preference() else BG)
    app=dialog._root()
    def sync_dialog(event=None):
        if hasattr(app,'_sync_theme'):app._sync_theme()
        dialog.configure(background='#dbeefa' if theme_preference() else BG)
    dialog.bind('<FocusIn>',sync_dialog,add='+')


def style_listbox(widget):
    register_widget(widget,'list')

def lock_controls(owner):
    """Remember semantic disabled/readonly flags; ignore transient hover/focus."""
    result=[]
    def walk(widget):
        for child in widget.winfo_children():
            if isinstance(child,(ttk.Button,ttk.Checkbutton,ttk.Radiobutton,ttk.Entry,ttk.Combobox,ttk.Spinbox,ttk.Menubutton,ttk.Scale)):
                result.append((child,child.instate(['disabled']),child.instate(['readonly'])));child.state(['disabled'])
            walk(child)
    walk(owner);return result

def unlock_controls(snapshot):
    for widget,disabled,readonly in snapshot:
        if widget.winfo_exists():widget.state(['disabled' if disabled else '!disabled','readonly' if readonly else '!readonly'])

def start_progress(progress):
    progress.configure(mode='indeterminate');progress.start(12)

def stop_progress(progress):
    progress.stop();progress.configure(mode='determinate',value=0)
