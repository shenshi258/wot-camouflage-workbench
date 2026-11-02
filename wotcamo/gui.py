from pathlib import Path
import os
import queue
import threading
import traceback
import subprocess
import sys
from .light_tooltips import HoverHelp
from .workbench_help import TEXT as HELP_TEXT, topic
from .ui_theme import configure_theme, build_header, BG, register_widget, style_listbox, lock_controls, unlock_controls, start_progress, stop_progress
from . import APP_NAME
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from .common import ROOT, settings, read_json, write_json, title_name
from . import wotdata, pipeline, modpack, models, autosave


class Workbench(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1200x850")
        self.minsize(1040, 750)
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        configure_theme(self)
        self.hover_help = HoverHelp(self)
        self.cfg = settings()
        self.events = queue.Queue()
        self.busy = False
        self._closing = False
        self._busy_controls = []
        self.index_data = {}
        self.buttons = []
        self.last_backup = None
        self.paint_sessions = []
        self._paint_after = None
        self.auto_save = tk.BooleanVar(value=autosave.enabled('texture'))
        self.output = tk.StringVar()
        self.project = tk.StringVar()
        # Keep the navigation labels in fixed-size controls. Selection changes
        # only colours, so a tab never shrinks or shifts its neighbours.
        self.configure(background='#f5f5f7')
        style = ttk.Style(self)
        outer = ttk.Frame(self, padding=(24, 14), style='Backdrop.TFrame')
        outer.pack(fill='both', expand=True)

        self.status = tk.StringVar(value='涂装制作  ·  模型编辑  ·  灯效与动画')
        header = build_header(outer,textvariable=self.status)
        header.pack(fill='x', pady=(0, 8))

        vehicle_card = ttk.Frame(outer, style='Panel.TFrame', padding=(16, 8))
        vehicle_card.pack(fill='x', pady=(0, 8))
        ttk.Label(vehicle_card, text='车型', style='Section.TLabel').pack(side='left', padx=(0, 14))
        self.query = tk.StringVar()
        self.hint(ttk.Entry(vehicle_card, textvariable=self.query, width=18), '搜索车型').pack(side='left', padx=(0, 8))
        self.tank = tk.StringVar(value='russian/R45_IS-7')
        self.tanks = ttk.Combobox(vehicle_card, textvariable=self.tank, state='readonly', width=42)
        self.hint(self.tanks, '选择车型').pack(side='left', fill='x', expand=True)
        self.tanks.bind('<<ComboboxSelected>>', lambda e: self.refresh_models())
        self.button(vehicle_card, '重建车型索引', self.reindex).pack(side='right', padx=(10, 0))
        self.query.trace_add('write', lambda *a: self.filter_tanks())

        section = ttk.Frame(outer, style='Panel.TFrame')
        section.pack(fill='both', expand=True)
        nav_wrap = ttk.Frame(section, padding=(18, 8, 18, 0), style='Card.TFrame')
        nav_wrap.pack(fill='x')
        nav = tk.Frame(nav_wrap, bg='#ededf0', padx=3, pady=3, highlightthickness=0)
        register_widget(nav,'nav')
        nav.pack(anchor='w')
        self.nav_var = tk.IntVar(value=0)
        self.nav_buttons = []
        self.nav_pages = []
        self.nav_shells = []
        self.page_viewports = []
        pages = ttk.Frame(section, style='Card.TFrame')
        pages.pack(fill='both', expand=True)
        pages.rowconfigure(0, weight=1); pages.columnconfigure(0, weight=1)
        for index, label in enumerate(('涂装制作', '模型修改', '灯效制作', 'AE特效导入', '设置与说明')):
            shell=ttk.Frame(pages,style='Card.TFrame');shell.grid(row=0,column=0,sticky='nsew')
            viewport=tk.Canvas(shell,background='#ffffff',highlightthickness=0)
            register_widget(viewport,'surface')
            scroll=ttk.Scrollbar(shell,orient='vertical',command=viewport.yview);viewport.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right',fill='y');viewport.pack(side='left',fill='both',expand=True)
            page = ttk.Frame(viewport, padding=(20, 12, 20, 12), style='Card.TFrame')
            item=viewport.create_window((0,0),window=page,anchor='nw')
            def fit_page(event=None,canvas=viewport,inner=page,window=item):
                width=max(1,canvas.winfo_width());height=max(canvas.winfo_height(),inner.winfo_reqheight())
                canvas.itemconfigure(window,width=width,height=height);canvas.configure(scrollregion=(0,0,width,height))
            viewport.bind('<Configure>',fit_page);page.bind('<Configure>',fit_page)
            def scroll_page(event,canvas=viewport,inner=page):
                if str(event.widget).startswith(str(inner)) and not isinstance(event.widget,(tk.Text,tk.Listbox,ttk.Combobox)):
                    canvas.yview_scroll(-int(event.delta/120),'units')
            self.bind('<MouseWheel>',scroll_page,add='+')
            self.nav_shells.append(shell);self.page_viewports.append(viewport)
            self.nav_pages.append(page)
            button = ttk.Radiobutton(nav, text=label, width=13, variable=self.nav_var,
                                     value=index, style='Scope.TRadiobutton',
                                     command=lambda i=index: self.select_page(i), takefocus=True)
            self.hint(button, label)
            button.grid(row=0, column=index, padx=1)
            self.nav_buttons.append(button)
        self.texture_ui(self.nav_pages[0])
        self.model_ui(self.nav_pages[1])
        self.light_ui(self.nav_pages[2])
        self.ae_ui(self.nav_pages[3])
        self.settings_ui(self.nav_pages[4])
        self.select_page(0)

        delivery = ttk.Frame(outer, style='Panel.TFrame', padding=(14, 11))
        delivery.pack(fill='x', pady=(12, 0))
        ttk.Label(delivery, text='当前产物', style='Section.TLabel').pack(side='left')
        self.hint(ttk.Entry(delivery, textvariable=self.output), '当前产物').pack(side='left', fill='x', expand=True, padx=10)
        self.button(delivery, '选择产物', self.choose_output).pack(side='left')
        self.button(delivery, '校验', self.verify).pack(side='left', padx=6)
        self.button(delivery, '安装到游戏（备份）', self.install).pack(side='left')
        self.button(delivery, '回滚安装', self.rollback).pack(side='left', padx=(6, 0))
        log_header = ttk.Frame(outer, style='Backdrop.TFrame')
        ttk.Label(log_header, text='操作记录', style='Canvas.TLabel').pack(side='left', padx=(0, 10))
        self.progress = ttk.Progressbar(log_header, mode='determinate', length=110)
        self.hint(self.progress, '进度'); self.progress.pack(side='right', padx=(10, 0))
        self.logs = tk.Text(log_header, height=2, wrap='word', bg='#ffffff', fg='#51515a',
                            font=('Microsoft YaHei UI', 9), relief='flat', padx=10, pady=4,
                            highlightthickness=1, highlightbackground='#e5e5ea')
        register_widget(self.logs,'field')
        self.hint(self.logs, '操作日志'); self.logs.pack(side='left', fill='x', expand=True)
        # Reserve the footer first; the editable page absorbs height changes.
        section.pack_forget(); delivery.pack_forget()
        log_header.pack(side='bottom', fill='x', pady=(7, 0))
        delivery.pack(side='bottom', fill='x', pady=(8, 0))
        section.pack(side='top', fill='both', expand=True)
        self.attach_label_hints(self)
        self._drain_after = self.after(100, self.drain)
        self._autosave_after = self.after(autosave.INTERVAL_MS, self.autosave_tick)
        self._paint_after = self.after(200, self.poll_paint_sessions)
        try:
            self.index_data = wotdata.load_index(self.cfg)["vehicles"]
            self.filter_tanks()
            self.refresh_models()
            self.log(f"就绪：{len(self.index_data)} 台车型；客户端 {wotdata.game_version(self.cfg['wot_root'])}")
            projects = sorted((ROOT / "projects").glob("*/project.json"), key=lambda p: p.stat().st_mtime)
            outputs = sorted((ROOT / "result").glob("*/report.json"), key=lambda p: p.stat().st_mtime)
            if projects:
                self.project.set(str(projects[-1].parent))
            if outputs:
                self.show_output(outputs[-1].parent)
        except Exception as e:
            if not self.cfg.get("wot_root"):
                self.log("请先在“设置与说明”选择并保存游戏客户端，再重建车型索引。")
            elif isinstance(e, FileNotFoundError):
                self.log("尚未建立车型索引，请点击“重建车型索引”。")
            else:
                self.log(str(e) + "。请核对客户端并重建车型索引。")

    def change_autosave(self):
        try: autosave.set_enabled('texture', self.auto_save.get())
        except OSError as e: self.log('自动保存开关未能记住：' + str(e))

    def autosave_tick(self):
        self._autosave_after = None
        try:
            if self.auto_save.get():
                data = dict(tank=self.tank.get(), query=self.query.get(), title=self.title_var.get(),
                            materials=self.materials.get(), prompt=self.prompt.get('1.0', 'end-1c'),
                            derive=self.derive.get(), do_pack=self.do_pack.get())
                path = autosave.save_draft(data)
                self.log('涂装草稿已自动保存：' + str(path))
        except Exception as e: self.log('涂装草稿自动保存失败：' + str(e))
        finally: self._autosave_after = self.after(autosave.INTERVAL_MS, self.autosave_tick)

    def restore_draft(self):
        folder = autosave.FOLDER / '涂装草稿'
        path = filedialog.askopenfilename(title='选择自动保存的涂装草稿', initialdir=str(folder if folder.exists() else ROOT), filetypes=[('涂装草稿', '*.json')])
        if not path: return
        try:
            d = autosave.load_draft(path)
            if not all(isinstance(d.get(k), str) for k in ('tank','query','title','materials','prompt')) or not all(type(d.get(k)) is bool for k in ('derive','do_pack')):
                raise ValueError('草稿字段不完整。')
            self.query.set(d['query']); self.tank.set(d['tank']); self.title_var.set(d['title']); self.materials.set(d['materials'])
            self.prompt.delete('1.0', 'end'); self.prompt.insert('1.0', d['prompt'])
            self.derive.set(d['derive']); self.do_pack.set(d['do_pack']); self.refresh_models()
            self.log('已恢复涂装草稿：' + path)
        except (OSError, ValueError, TypeError) as e: messagebox.showerror('恢复失败', str(e), parent=self)

    def open_paint_preview(self, use_package=False):
        """在后台准备当前车型，界面线程只接收并管理预览窗口。"""
        if self.busy:return
        try:
            from . import light_effects
            client=str(light_effects.resolve_client_root(self.cfg.get('wot_root','')))
            tank=self.tank.get()
            if tank not in wotdata.load_index(self.cfg)['vehicles']:
                raise ValueError('请先重建索引并选择车型。')
            title=title_name(self.title_var.get())
        except (OSError,ValueError,KeyError) as error:
            messagebox.showerror('无法打开三维贴图',str(error),parent=self);return
        package=None
        if use_package:
            package=filedialog.askopenfilename(title='选择当前车型的涂装包',filetypes=[('WOT 涂装包','*.wotmod')])
            if not package:return
        def create():
            import tempfile
            from . import paint3d,preview3d
            cache=ROOT/'.cache';cache.mkdir(exist_ok=True)
            folder=Path(tempfile.mkdtemp(prefix='paint3d_',dir=cache))
            project=paint3d.project_from_package(tank,package) if package else paint3d.create_stock_project(tank,folder)
            return preview3d.Session(project,client,paint={'title':title})
        def opened(session):
            self.paint_sessions.append(session)
            self.log('三维贴图窗口已打开：点击模型并导入图片，顺序不限。')
        self.task(create,opened)

    def poll_paint_sessions(self):
        """回到界面线程汇报导出结果，并回收已关闭的预览会话。"""
        self._paint_after=None
        for session in self.paint_sessions[:]:
            if session.viewer and session.viewer.poll() is not None:
                code=session.viewer.returncode;session.close();self.paint_sessions.remove(session)
                self.log('三维贴图窗口已关闭。' if code==0 else '三维贴图窗口退出；请检查 WebView2 Runtime。')
                continue
            try:
                while True:
                    event=session.events.get_nowait()
                    if event.get('type')=='paint_complete':
                        self.log('已生成三维贴图待测包：'+event['target'])
                        messagebox.showinfo('三维贴图已生成',event['target']+'\n\nSHA256：'+event['sha256']+'\n\n请在实际客户端检查整车加载与贴图效果。',parent=self)
            except queue.Empty:pass
        self._paint_after=self.after(200,self.poll_paint_sessions)

    def select_page(self, index):
        self.nav_var.set(index)
        self.nav_shells[index].tkraise()
        self.current_page = index

    def button(self, parent, label, callback, accent=False):
        b = ttk.Button(parent, text=label, command=callback, style="Accent.TButton" if accent else "TButton")
        self.buttons.append(b)
        if label in HELP_TEXT:
            self.hint(b, label)
        return b

    def hint(self, widget, name):
        self.hover_help.attach(widget, lambda event: topic(name))
        return widget

    def attach_label_hints(self, parent):
        for widget in parent.winfo_children():
            if isinstance(widget, (ttk.Label, ttk.Checkbutton)):
                name = str(widget.cget('text'))
                if name in HELP_TEXT:
                    self.hint(widget, name)
            self.attach_label_hints(widget)

    def log(self, message):
        self.logs.insert("end", str(message)+"\n")
        self.logs.see("end")

    def worker_log(self, message):
        self.events.put(("log", str(message)))

    def task(self, function, done=None):
        if self.busy:
            self.log("正在处理，请等待当前操作完成。")
            return
        self.busy = True
        start_progress(self.progress)
        self._busy_controls = lock_controls(self)
        def run():
            try:
                result = function()
                self.events.put(("done", (done, result)))
            except Exception as e:
                (ROOT / ".cache").mkdir(exist_ok=True)
                (ROOT / ".cache/last_error.log").write_text(traceback.format_exc(), encoding="utf-8")
                self.events.put(("error", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def drain(self):
        self._drain_after = None
        try:
            while not self.events.empty():
                kind,value=self.events.get_nowait()
                if kind=='log':self.log(value);continue
                self.busy=False;stop_progress(self.progress);unlock_controls(self._busy_controls);self._busy_controls=[]
                if kind=='error':self.log('操作失败：'+value);messagebox.showerror('操作未完成',value,parent=self)
                else:
                    callback,result=value
                    if callback:callback(result)
        except Exception as error:
            self.busy=False;stop_progress(self.progress);unlock_controls(self._busy_controls);self._busy_controls=[]
            self.log('界面更新失败：'+str(error))
            messagebox.showerror('界面更新未完成',str(error),parent=self)
        finally:
            if not self._closing:self._drain_after=self.after(100,self.drain)

    def destroy(self):
        self._closing = True
        if getattr(self, "_paint_after", None):
            self.after_cancel(self._paint_after); self._paint_after=None
        for session in getattr(self,"paint_sessions",[]): session.close()
        self.paint_sessions=[]
        if getattr(self, "_autosave_after", None):
            self.after_cancel(self._autosave_after); self._autosave_after = None
        if getattr(self, "_drain_after", None):
            self.after_cancel(self._drain_after)
            self._drain_after = None
        super().destroy()

    def filter_tanks(self):
        values = [x for x in sorted(self.index_data) if self.query.get().lower() in x.lower()]
        self.tanks["values"] = values
        if values and self.tank.get() not in values:
            self.tank.set(values[0])
            self.refresh_models()

    def reindex(self):
        def done(values):
            self.index_data = values
            self.filter_tanks()
            self.refresh_models()
        self.task(lambda: wotdata.index(self.cfg["wot_root"], self.cfg["index_file"], self.worker_log), done)

    def texture_ui(self, page):
        page.columnconfigure(0, weight=6, uniform='content')
        page.columnconfigure(1, weight=4, uniform='content')
        page.rowconfigure(1, weight=1)
        title = ttk.Frame(page, style='Card.TFrame'); title.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 8))
        ttk.Label(title, text='涂装制作', style='PageTitle.TLabel', font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(title, text='制作基础涂装，或直接在三维模型上放置图片。', style='PageSubtitle.TLabel').pack(anchor='w', pady=(3, 0))
        left = ttk.Frame(page, style='Card.TFrame'); left.grid(row=1, column=0, sticky='nsew', padx=(0, 22))
        ttk.Label(left, text='基础涂装', style='Section.TLabel').pack(anchor='w', pady=(0, 3))
        ttk.Label(left, text='作品名称', style='Field.TLabel').pack(anchor='w')
        self.title_var = tk.StringVar(value='沙漠之冠')
        self.hint(ttk.Entry(left, textvariable=self.title_var), '作品名称').pack(fill='x', pady=(3, 5))
        ttk.Label(left, text='素材文件夹', style='Field.TLabel').pack(anchor='w')
        row = ttk.Frame(left, style='Card.TFrame'); row.pack(fill='x', pady=(3, 5))
        self.materials = tk.StringVar(value=str(ROOT / 'materials/demo'))
        self.hint(ttk.Entry(row, textvariable=self.materials), '素材文件夹').pack(side='left', fill='x', expand=True)
        self.hint(self.button(row, '浏览', lambda: self.browse_dir(self.materials)), '素材浏览').pack(side='left', padx=(6, 0))
        ttk.Label(left, text='中文制作要求', style='Field.TLabel').pack(anchor='w')
        self.prompt = tk.Text(left, height=3, wrap='word', font=('Microsoft YaHei UI', 10),
                              bg='#fafafa', fg='#1d1d1f', relief='flat', padx=10, pady=7,
                              highlightthickness=1, highlightbackground='#e2e2e7', highlightcolor='#007aff')
        register_widget(self.prompt,'field')
        self.hint(self.prompt, '中文制作要求'); self.prompt.pack(fill='both', expand=True, pady=(4, 6))
        self.prompt.insert('1.0', '沙漠黄底色 + 白色虎纹 + 中度做旧，贴上 badge_rose.png 和 number_07.png，哑光，屏蔽官方涂装')
        options = ttk.Frame(left, style='Card.TFrame'); options.pack(fill='x')
        self.derive = tk.BooleanVar(value=True); self.do_pack = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text='按要求派生 AO / GMM / ANM', variable=self.derive).pack(side='left')
        ttk.Checkbutton(options, text='生成 .wotmod', variable=self.do_pack).pack(side='left', padx=(14, 0))
        self.hint(options.winfo_children()[-1], '同时生成 .wotmod 安装包')
        actions = ttk.Frame(left, style='Card.TFrame')
        self.button(actions, '生成涂装包', self.build, True).pack(side='left')
        self.button(actions, '用配方文件生成', self.build_recipe).pack(side='left', padx=8)
        autosave_menu = ttk.Menubutton(actions, text='自动保存')
        menu = tk.Menu(autosave_menu, tearoff=False)
        register_widget(menu,'menu')
        menu.add_checkbutton(label='每 5 分钟自动保存草稿', variable=self.auto_save, command=self.change_autosave)
        menu.add_command(label='恢复涂装草稿', command=self.restore_draft)
        autosave_menu.configure(menu=menu); autosave_menu.pack(side='left')
        # Reserve actions before the growing text field, especially at minimum height.
        self.prompt.pack_forget(); options.pack_forget()
        actions.pack(side='bottom', fill='x', pady=(8, 0))
        options.pack(side='bottom', fill='x')
        self.prompt.pack(fill='both', expand=True, pady=(4, 6))
        # Both entry points lead to the same editor; keep them visible so the
        # user can choose a stock model or an existing skin without a hidden menu.
        right = ttk.Frame(page, style='Panel.TFrame', padding=14)
        right.grid(row=1, column=1, sticky='nsew')
        ttk.Label(right, text='三维模型贴图', style='Section.TLabel').pack(anchor='w')
        ttk.Label(right, text='点击车体，导入图片并实时调整位置。', style='PageSubtitle.TLabel',
                  wraplength=300).pack(anchor='w', pady=(4, 9))
        paint_actions=ttk.Frame(right,style='Card.TFrame');paint_actions.pack(fill='x')
        self.button(paint_actions,'打开原版模型',lambda:self.open_paint_preview(False),True).pack(side='left')
        self.button(paint_actions,'打开已有涂装',lambda:self.open_paint_preview(True)).pack(side='left',padx=(7,0))
        ttk.Separator(right,orient='horizontal').pack(fill='x',pady=12)
        atlas_head=ttk.Frame(right,style='Card.TFrame');atlas_head.pack(fill='x')
        ttk.Label(atlas_head,text='图集预览',style='Section.TLabel').pack(side='left')
        ttk.Label(atlas_head,text='AM 贴图',style='PageSubtitle.TLabel').pack(side='right')
        self.preview_label = ttk.Label(right, text='生成基础涂装后\n在这里查看贴图图集',
                                       anchor='center', justify='center', style='PageSubtitle.TLabel')
        self.hint(self.preview_label, '贴图预览'); self.preview_label.pack(fill='both', expand=True, pady=8)
        self.button(right, '打开产物文件夹', lambda: self.open_folder(self.output.get())).pack(anchor='w')

    def build(self, recipe_file=None):
        tank, mat, text, title = self.tank.get(), self.materials.get(), self.prompt.get("1.0", "end").strip(), self.title_var.get()
        derive, pack = self.derive.get(), self.do_pack.get()
        def run():
            out = pipeline.build(tank, mat, text, title, self.cfg, derive_maps=derive, do_pack=pack, recipe_file=recipe_file, log=self.worker_log)
            pipeline.verify(out, self.cfg, self.worker_log)
            return out
        self.task(run, self.show_output)

    def build_recipe(self):
        path = filedialog.askopenfilename(title="选择 recipe.json", filetypes=[("JSON 配方", "*.json")], initialdir=str(ROOT / "result"))
        if path:
            self.build(path)

    def model_ui(self, page):
        ttk.Label(page, text='模型修改', style='PageTitle.TLabel', font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(page, text='选择部件，创建工程，在 Blender 中编辑后导出。', style='PageSubtitle.TLabel').pack(anchor='w', pady=(3, 12))
        line = ttk.Frame(page, style='Card.TFrame'); line.pack(fill='x')
        ttk.Label(line, text='原版模型部件', style='Section.TLabel').pack(side='left')
        self.all_lods = tk.BooleanVar()
        ttk.Checkbutton(line, text='显示全部 LOD 和 3D 皮肤变体', variable=self.all_lods, command=self.refresh_models).pack(side='right')
        models_box = ttk.Frame(page, style='Panel.TFrame')
        self.model_list = tk.Listbox(models_box, height=5, exportselection=False, font=('Microsoft YaHei UI', 10),
                                     bg='#fafafa', fg='#1d1d1f', selectbackground='#e5f0ff', selectforeground='#0062cc',
                                     relief='flat', borderwidth=0, highlightthickness=0, activestyle='none')
        style_listbox(self.model_list)
        self.hint(self.model_list, '模型部件列表'); self.model_list.pack(side='left', fill='both', expand=True, padx=(8, 0), pady=6)
        scroll = ttk.Scrollbar(models_box, command=self.model_list.yview); scroll.pack(side='right', fill='y')
        self.model_list.configure(yscrollcommand=scroll.set)
        actions = ttk.Frame(page, style='Card.TFrame')
        self.button(actions, '创建模型工程', self.create_model, True).pack(side='left')
        self.button(actions, '在 Blender 中编辑', self.open_model).pack(side='left', padx=8)
        self.button(actions, '导出模型并打包', self.export_model).pack(side='left')
        self.button(actions, '应用当前涂装到模型预览', self.apply_model_texture).pack(side='left', padx=8)
        project_row = ttk.Frame(page, style='Card.TFrame')
        ttk.Label(project_row, text='模型工程', style='Field.TLabel').pack(side='left')
        self.hint(ttk.Entry(project_row, textvariable=self.project), '模型工程').pack(side='left', fill='x', expand=True, padx=10)
        self.button(project_row, '选择已有工程', lambda: self.browse_dir(self.project, ROOT / 'projects')).pack(side='left')
        ttk.Label(page, text='每个工程对应一个部件和 LOD；导出后的游戏效果仍需实测。', style='PageSubtitle.TLabel').pack(side='bottom', anchor='w', pady=(8, 0))
        project_row.pack(side='bottom', fill='x')
        actions.pack(side='bottom', fill='x', pady=(0, 10))
        package_row=ttk.Frame(page,style='Card.TFrame');package_row.pack(side='bottom',fill='x',pady=(0,8))
        ttk.Label(package_row,text='模型包名称',style='Field.TLabel').pack(side='left')
        self.model_package_title=tk.StringVar()
        self.hint(ttk.Entry(package_row,textvariable=self.model_package_title),'填写导出 .wotmod 包的名称；留空使用工程保存的名称').pack(side='left',fill='x',expand=True,padx=10)
        models_box.pack(fill='both', expand=True, pady=(8, 10))

    def ae_ui(self, page):
        ttk.Label(page,text='AE 特效导入',style='PageTitle.TLabel').pack(anchor='w')
        ttk.Label(page,text='套用 35 款内置预设，或导入透明 PNG；支持装甲吸附、裁剪及贴面横纵独立缩放。',style='PageSubtitle.TLabel',wraplength=850).pack(anchor='w',pady=(6,18))
        card=ttk.Frame(page,style='Panel.TFrame',padding=18);card.pack(fill='x')
        ttk.Label(card,text='使用自己的特效素材',style='Section.TLabel').pack(anchor='w')
        ttk.Label(card,text='支持帧率、尺寸、位置、朝向、亮度及透明混合调整；可保存工程后继续编辑。',style='PageSubtitle.TLabel').pack(anchor='w',pady=10)
        self.button(card,'打开 AE 特效导入',self.open_ae,True).pack(anchor='w')
        ttk.Label(page,text='AE 请选择 RGB＋Alpha，推荐直通透明。预览与导出共用帧序、尺寸和混合方式；游戏曝光与泛光仍需实测。',style='PageSubtitle.TLabel',wraplength=850).pack(anchor='w',pady=18)

    def open_ae(self):
        flags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0
        subprocess.Popen([sys.executable,'-m','wotcamo.ae_gui','--client',self.cfg.get('wot_root','')],cwd=str(ROOT),creationflags=flags)
        self.log('已打开 AE 特效导入窗口。')

    def light_ui(self, page):
        ttk.Label(page, text='灯效制作', style='PageTitle.TLabel', font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(page, text='导入涂装，框选区域或灯面，再设置光效配方。', style='PageSubtitle.TLabel').pack(anchor='w', pady=(3, 15))
        card = ttk.Frame(page, style='Panel.TFrame', padding=18)
        card.pack(fill='x')
        ttk.Label(card, text='灯效制作器  ·  3.3', style='Section.TLabel').pack(anchor='w')
        ttk.Label(card, text='在独立编辑窗口中选择灯面、预览效果并生成待测包。', style='PageSubtitle.TLabel', wraplength=850).pack(anchor='w', pady=(5, 12))
        row = ttk.Frame(card, style='Card.TFrame'); row.pack(anchor='w')
        self.button(row, '打开灯效制作器', lambda: self.open_light(False), True).pack(side='left')
        self.button(row, '将当前涂装交给灯效制作器', lambda: self.open_light(True)).pack(side='left', padx=8)
        self.button(row, '查看灯效使用说明', lambda: os.startfile(str(ROOT / 'reference/灯效制作器使用说明.md'))).pack(side='left')
        ttk.Label(page, text='请确认实际客户端和原版基线；预览及文件校验不能代替游戏内验收。', style='PageSubtitle.TLabel', wraplength=900).pack(anchor='w', pady=(14, 0))

    def open_light(self, handoff):
        args = []
        if handoff:
            folder = Path(self.output.get())
            packages = sorted(folder.glob('*.wotmod')) if folder.is_dir() else []
            if len(packages) == 1:
                path = str(packages[0])
            else:
                path = filedialog.askopenfilename(title='选择要交接的涂装包', initialdir=str(folder if folder.is_dir() else ROOT), filetypes=[('WOT 涂装', '*.wotmod *.zip')])
            if not path: return
            args = ['--source', path]
        try:
            subprocess.Popen([sys.executable, '-m', 'wotcamo.light_gui', *args], cwd=str(ROOT))
            self.log('已打开灯效制作器；请在灯效窗口确认实际客户端与原版基线。')
        except OSError as error:
            messagebox.showerror('无法打开灯效制作器', str(error))

    def refresh_models(self):
        if not hasattr(self, "model_list"):
            return
        self.model_paths = sorted(p for p in self.index_data.get(self.tank.get(), {}) if p.lower().endswith(".model") and (self.all_lods.get() or ("/normal/lod0/" in p and "/_skins/" not in p)))
        self.model_list.delete(0, "end")
        for path in self.model_paths:
            self.model_list.insert("end", path.split(self.tank.get()+"/")[-1])
        preferred = next((i for i, p in enumerate(self.model_paths) if Path(p).name.lower() == "hull.model"), 0)
        if self.model_paths:
            self.model_list.selection_set(preferred)

    def create_model(self):
        selected = self.model_list.curselection()
        if not selected:
            return messagebox.showinfo("选择模型", "请在列表中选择部件")
        tank, rel = self.tank.get(), self.model_paths[selected[0]]
        self.task(lambda: models.create(tank, rel, self.cfg, self.worker_log), lambda p: self.project.set(str(p)))

    def open_model(self):
        try:
            models.open_project(self.project.get(), self.cfg)
        except Exception as e:
            messagebox.showerror("无法打开工程", str(e))

    def export_model(self):
        project = self.project.get();name=self.model_package_title.get().strip() or None
        self.task(lambda: models.export(project, self.cfg, self.worker_log,title=name), self.show_output)

    def apply_model_texture(self):
        project, output = self.project.get(), self.output.get()
        self.task(lambda: models.apply_textures(project, output, self.cfg, self.worker_log))

    def settings_ui(self, page):
        ttk.Label(page, text='设置与说明', style='PageTitle.TLabel', font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(page, text='配置实际游戏客户端和模型编辑工具。', style='PageSubtitle.TLabel').pack(anchor='w', pady=(3, 12))
        self.settings_vars = {}
        for key, label in (('wot_root', '坦克世界客户端根目录'), ('blender', 'Blender 程序')):
            ttk.Label(page, text=label, style='Field.TLabel').pack(anchor='w', pady=(0, 4))
            row = ttk.Frame(page, style='Card.TFrame'); row.pack(fill='x', pady=(0, 9))
            var = tk.StringVar(value=self.cfg[key]); self.settings_vars[key] = var
            self.hint(ttk.Entry(row, textvariable=var), label).pack(side='left', fill='x', expand=True)
            if key == 'blender':
                self.hint(self.button(row, '浏览', lambda v=var: self.browse_exe(v)), 'Blender浏览').pack(side='left', padx=(8, 0))
            else:
                self.hint(self.button(row, '浏览', lambda v=var: self.browse_dir(v)), '客户端浏览').pack(side='left', padx=(8, 0))
        row = ttk.Frame(page, style='Card.TFrame'); row.pack(fill='x', pady=(2, 14))
        self.button(row, '保存设置', self.save_settings, True).pack(side='left')
        self.button(row, '打开完整使用说明', lambda: os.startfile(str(ROOT / 'README.md'))).pack(side='left', padx=8)
        ttk.Label(page, text='使用提示', style='Section.TLabel').pack(anchor='w')
        ttk.Label(page, text='产物与模型工程保存在工作台内；安装前自动校验并备份。更换客户端或更新游戏后，请重建车型索引。', style='PageSubtitle.TLabel', wraplength=900).pack(anchor='w', pady=(5, 0))

    def save_settings(self):
        cfg = read_json(ROOT / "config/settings.json")
        for key, var in self.settings_vars.items():
            cfg[key] = var.get().replace("\\", "/")
        write_json(ROOT / "config/settings.json", cfg)
        self.cfg = settings()
        self.log("设置已保存。更换客户端后请重建索引。")

    def browse_dir(self, var, initial=None):
        path = filedialog.askdirectory(initialdir=str(initial or ROOT))
        if path:
            var.set(path)

    def browse_exe(self, var):
        path = filedialog.askopenfilename(filetypes=[("Blender", "blender.exe")])
        if path:
            var.set(path)

    def choose_output(self):
        path = filedialog.askdirectory(initialdir=str(ROOT / "result"))
        if path:
            self.show_output(Path(path))

    def show_output(self, path):
        self.output.set(str(path))
        imfile = Path(path) / "preview.png"
        if imfile.is_file():
            with Image.open(imfile) as im:
                im.thumbnail((400, 300))
                self.preview_image = ImageTk.PhotoImage(im.copy())
            self.preview_label.configure(image=self.preview_image, text="")
        self.log("产物已就绪；可校验、打开文件夹或安装到游戏。")

    def open_folder(self, path):
        if path and Path(path).is_dir():
            os.startfile(str(Path(path).resolve()))

    def verify(self):
        path = self.output.get()
        self.task(lambda: pipeline.verify(path, self.cfg, self.worker_log))

    def install(self):
        path = self.output.get()
        def run():
            pipeline.verify(path, self.cfg, self.worker_log)
            return modpack.install(path, self.cfg["wot_root"], self.worker_log)
        self.task(run, lambda p: setattr(self, "last_backup", p))

    def rollback(self):
        path = filedialog.askdirectory(title="选择要回滚的安装记录", initialdir=str(ROOT / "backups"))
        if path:
            self.task(lambda: modpack.rollback(path, self.worker_log, wot_root=self.cfg["wot_root"]))


def main():
    app = Workbench()
    import sys
    if "--smoke" in sys.argv:
        app.update()
        assert len(app.index_data) > 0
        assert len(app.model_paths) > 0
        assert app.winfo_width() >= 1040
        print(f"GUI_OK vehicles={len(app.index_data)} model_options={len(app.model_paths)}")
        app.destroy()
    else:
        app.mainloop()


if __name__ == "__main__":
    main()
