"""Native node editor for motion inside an imported image/GIF canvas."""
import copy
import math
import tkinter as tk
from tkinter import messagebox, ttk

from . import ae_animation
from .light_help import Help
from .light_tooltips import HoverHelp
from .ui_theme import prepare_dialog, register_widget


EASING_LABELS = {'线性': 'linear', '平滑': 'smooth', '保持': 'hold'}
EASING_NAMES = {value: key for key, value in EASING_LABELS.items()}
FIELD_LABELS = (('time', '时间（秒）'), ('x', '横移（%）'), ('y', '纵移（%）'),
                ('rotation', '旋转（°）'), ('scale', '缩放（倍）'), ('opacity', '不透明度（%）'))


class AnimationDialog(tk.Toplevel):
    """Edit a private copy; only Apply publishes it to the parent editor.

    Preview also receives a validated copy, without applying parent settings.
    No modal grab is held: the parent's separate animation preview must retain
    its normal pause, replay and close controls.
    """
    def __init__(self, parent, animation, fps, on_apply, on_preview=None):
        normalized = ae_animation.normalize(animation)
        try:
            rate = float(fps)
        except (ValueError, TypeError, OverflowError):
            raise ValueError('动画帧率无效。')
        if isinstance(fps, bool) or not math.isfinite(rate) or not 1 <= rate <= 60:
            raise ValueError('动画帧率范围为 1～60 FPS。')
        if not callable(on_apply):
            raise ValueError('动画应用操作无效。')
        super().__init__(parent)
        prepare_dialog(self, '动画节点')
        self.transient(parent)
        width = min(860, max(680, self.winfo_screenwidth() - 70))
        height = min(650, max(500, self.winfo_screenheight() - 95))
        self.geometry('%dx%d' % (width, height)); self.minsize(640, 480)
        self.fps = rate; self.on_apply = on_apply; self.on_preview = on_preview
        self.nodes = copy.deepcopy(normalized['nodes'])
        self.selected_index = None; self.cursor_time = 0.0
        self._loading = False; self.draft_dirty = False
        self.parameters = {key: tk.StringVar(self, value=format(normalized[key], '.9g'))
                           for key in ('duration', 'canvas_scale')}
        self.node_vars = {key: tk.StringVar(self, value=format(ae_animation.DEFAULT_NODE[key], '.9g'))
                          for key, unused in FIELD_LABELS}
        self.easing = tk.StringVar(self, value='线性')
        self.status = tk.StringVar(self); self.cursor_label = tk.StringVar(self, value='当前时间 0 秒')
        self.fields = {}
        self.hover_help = HoverHelp(self)
        self.interface()
        help_text = dict(duration='循环时长为 0.1～60 秒。动画最多 128 帧，最终帧数由时长乘以主窗口帧率决定。',
                         canvas_scale='画布留白为 1～4 倍。保留原素材比例，增加留白可为移动和旋转腾出空间。',
                         time='节点在循环内的时间。同一时间只允许一个节点；调整已有节点请点击更新。',
                         x='横向位移占画布宽度的百分比，正值向右；范围 -200%～200%。',
                         y='纵向位移占画布高度的百分比，正值向上；范围 -200%～200%。',
                         rotation='围绕素材中心旋转，正值逆时针；范围 -3600°～3600°。',
                         scale='围绕素材中心缩放，范围 0.01～10 倍；超出画布的部分会裁切。',
                         opacity='保留原透明通道后乘以该不透明度，0% 不可见，100% 保留原透明度。')
        for key, field in self.fields.items():
            title=dict(FIELD_LABELS,duration='循环时长',canvas_scale='画布留白')[key]
            self.hover_help.attach(field, lambda event, text=help_text[key],title=title: Help(title,text))
        self.hover_help.attach(self.easing_combo, lambda event: Help('节点过渡','本节点到下个节点的过渡：线性匀速，平滑先慢后快再慢，保持直到下个节点再切换。'))
        self.hover_help.attach(self.preview_button, lambda event: Help('播放预览','预览当前已更新的节点，不把设置应用到父窗口。'))
        self.hover_help.attach(self.apply_button, lambda event: Help('应用动画节点','保存当前节点设置到 AE 编辑窗口，导出时烘焙为同一组动画帧。'))
        for variable in self.parameters.values():
            variable.trace_add('write', self.refresh)
        for variable in list(self.node_vars.values()) + [self.easing]:
            variable.trace_add('write', self._draft_changed)
        self._fill_list()
        self.refresh()
        self.protocol('WM_DELETE_WINDOW', self.destroy)

    def interface(self):
        box = ttk.Frame(self, padding=14, style='Backdrop.TFrame'); box.pack(fill='both', expand=True)
        # Reserve the footer first. Every edit remains reachable by scrolling on
        # an 800x600 desktop, while Apply/Cancel never leave the visible window.
        footer = ttk.Frame(box, padding=(0, 10, 0, 0)); footer.pack(side='bottom', fill='x')
        self.status_label = ttk.Label(footer, textvariable=self.status, wraplength=720)
        self.status_label.pack(anchor='w', fill='x', pady=(0, 8))
        actions = ttk.Frame(footer); actions.pack(fill='x')
        self.cancel_button = ttk.Button(actions, text='取消', command=self.destroy)
        self.cancel_button.pack(side='right')
        self.apply_button = ttk.Button(actions, text='应用动画节点', style='Accent.TButton', command=self.apply)
        self.apply_button.pack(side='right', padx=8)
        self.preview_button = ttk.Button(actions, text='播放预览', command=self.preview)
        self.preview_button.pack(side='left')
        footer.bind('<Configure>', lambda event: self.status_label.configure(wraplength=max(360, event.width - 8)))

        outer = ttk.Frame(box); outer.pack(fill='both', expand=True)
        self.body_canvas = tk.Canvas(outer, highlightthickness=0, bg='#ffffff')
        register_widget(self.body_canvas, 'surface')
        scroll = ttk.Scrollbar(outer, orient='vertical', command=self.body_canvas.yview)
        self.body_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); self.body_canvas.pack(side='left', fill='both', expand=True)
        body = ttk.Frame(self.body_canvas, padding=(0, 0, 10, 0))
        item = self.body_canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda event: self.body_canvas.configure(scrollregion=self.body_canvas.bbox('all')))
        self.body_canvas.bind('<Configure>', lambda event: self.body_canvas.itemconfigure(item, width=event.width))

        ttk.Label(body, text='素材画布内的二维动画', style='Section.TLabel').pack(anchor='w')
        ttk.Label(body, text='图片可制作动画；GIF 原有播放保留，再叠加移动、旋转、缩放与淡入淡出。',
                  wraplength=710, style='Muted.TLabel').pack(anchor='w', pady=(4, 10))
        settings = ttk.Frame(body); settings.pack(fill='x')
        for column, (key, title) in enumerate((('duration', '循环时长（秒）'), ('canvas_scale', '画布留白（倍）'))):
            ttk.Label(settings, text=title).grid(row=0, column=column * 2, sticky='w', padx=(0, 7))
            field = ttk.Entry(settings, textvariable=self.parameters[key], width=9)
            field.grid(row=0, column=column * 2 + 1, sticky='w', padx=(0, 20)); self.fields[key] = field
        self.example_button = ttk.Button(settings, text='左右往返示例', command=self.example)
        self.example_button.grid(row=0, column=4, sticky='e'); settings.columnconfigure(4, weight=1)

        timeline_heading = ttk.Frame(body); timeline_heading.pack(fill='x', pady=(12, 0))
        ttk.Label(timeline_heading, text='点击时间轴定位，点击菱形选择节点', style='Muted.TLabel').pack(side='left')
        ttk.Label(timeline_heading, textvariable=self.cursor_label, style='Muted.TLabel').pack(side='right')
        self.timeline = tk.Canvas(body, height=58, highlightthickness=0, bg='#f4f7fb')
        register_widget(self.timeline, 'surface'); self.timeline.pack(fill='x', pady=(4, 9))
        self.timeline.bind('<Configure>', lambda event: self.draw_timeline())
        self.timeline.bind('<Button-1>', self.click_timeline)

        listing = ttk.Frame(body); listing.pack(fill='x')
        columns = ('time', 'x', 'y', 'rotation', 'scale', 'opacity', 'easing')
        self.node_list = ttk.Treeview(listing, columns=columns, show='headings', height=3, selectmode='browse')
        titles = ('时间 s', '横移 %', '纵移 %', '旋转 °', '缩放', '不透明 %', '过渡')
        for name, title in zip(columns, titles):
            self.node_list.heading(name, text=title)
            self.node_list.column(name, width=82 if name != 'easing' else 72, minwidth=58, anchor='center', stretch=True)
        tree_scroll = ttk.Scrollbar(listing, orient='vertical', command=self.node_list.yview)
        self.node_list.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side='right', fill='y'); self.node_list.pack(side='left', fill='x', expand=True)
        self.node_list.bind('<<TreeviewSelect>>', self.select_node)

        editor = ttk.LabelFrame(body, text='节点参数', padding=10); editor.pack(fill='x', pady=(10, 8))
        for index, (key, title) in enumerate(FIELD_LABELS):
            row, column = divmod(index, 3)
            field_group = ttk.Frame(editor); field_group.grid(row=row, column=column, sticky='ew', padx=(0, 10), pady=3)
            ttk.Label(field_group, text=title, width=13).pack(anchor='w')
            field = ttk.Entry(field_group, textvariable=self.node_vars[key], width=13)
            field.pack(fill='x'); self.fields[key] = field; editor.columnconfigure(column, weight=1)
        easing_row = ttk.Frame(editor); easing_row.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(6, 0))
        ttk.Label(easing_row, text='到下个节点的过渡').pack(side='left')
        self.easing_combo = ttk.Combobox(easing_row, textvariable=self.easing, values=list(EASING_LABELS), state='readonly', width=10)
        self.easing_combo.pack(side='left', padx=8)
        ttk.Label(easing_row, text='横移正值向右，纵移正值向上。', style='Muted.TLabel').pack(side='left')

        node_actions = ttk.Frame(body); node_actions.pack(fill='x')
        self.add_button = ttk.Button(node_actions, text='新增节点', command=self.add_node); self.add_button.pack(side='left')
        self.update_button = ttk.Button(node_actions, text='更新节点', command=self.update_node); self.update_button.pack(side='left', padx=8)
        self.delete_button = ttk.Button(node_actions, text='删除选中', command=self.delete_node); self.delete_button.pack(side='left')
        self.clear_button = ttk.Button(node_actions, text='清空节点', command=self.clear_nodes); self.clear_button.pack(side='right')
        ttk.Label(body, text='编辑字段后点击新增或更新。超出画布的部分会裁切，可增加画布留白；旋转、缩放以素材中心为基准。\n'
                            '首尾没有节点时保持最近姿态；循环从末尾回到开头，首尾姿态不同时会直接跳转。',
                  wraplength=710, style='Muted.TLabel').pack(anchor='w', pady=(9, 0))

        def wheel(event):
            if str(event.widget).startswith(str(body)) and event.widget is not self.node_list:
                self.body_canvas.yview_scroll(int(-event.delta / 120), 'units')
        self.bind('<MouseWheel>', wheel, add='+')

    def _draft_changed(self, *unused):
        if not self._loading:
            self.draft_dirty = True
        self.refresh()

    def _draft(self):
        node = {key: variable.get() for key, variable in self.node_vars.items()}
        if self.easing.get() not in EASING_LABELS:
            raise ValueError('请选择有效的节点过渡方式。')
        node['easing'] = EASING_LABELS[self.easing.get()]
        return node

    def collect(self):
        return ae_animation.normalize(dict(duration=self.parameters['duration'].get(),
                                           canvas_scale=self.parameters['canvas_scale'].get(),
                                           nodes=copy.deepcopy(self.nodes)))

    def _validated(self):
        config = self.collect()
        count = math.ceil(config['duration'] * self.fps - 1e-9)
        if config['nodes'] and count > 128:
            raise ValueError('当前需要 %d 帧，最多 128 帧；请缩短循环时长或返回主窗口降低帧率。' % count)
        return config, count

    def refresh(self, *unused):
        if not hasattr(self, 'apply_button'):
            return
        try:
            config, count = self._validated()
            if config['nodes']:
                text = '%d 个节点 · %d 帧 · %g FPS · 实际循环 %.3f 秒。' % (len(config['nodes']), count, self.fps, count / self.fps)
            else:
                text = '尚无动画节点：保留原图片／GIF，不改变原素材播放。'
            if self.draft_dirty:
                text += ' 字段有修改，请先新增或更新节点。'
            self.status.set(text); self.status_label.configure(foreground='#245b82')
            self.apply_button.state(['!disabled'])
            self.preview_button.state(['!disabled'] if self.on_preview else ['disabled'])
        except ValueError as error:
            self.status.set(str(error)); self.status_label.configure(foreground='#a62b30')
            self.apply_button.state(['disabled']); self.preview_button.state(['disabled'])
        chosen = self.selected_index is not None and self.selected_index < len(self.nodes)
        self.update_button.state(['!disabled'] if chosen else ['disabled'])
        self.delete_button.state(['!disabled'] if chosen else ['disabled'])
        self.clear_button.state(['!disabled'] if self.nodes else ['disabled'])
        self.draw_timeline()

    def _fill_list(self, select_time=None):
        self.node_list.delete(*self.node_list.get_children())
        self.selected_index = None
        for index, node in enumerate(self.nodes):
            values = [format(node[key], '.6g') for key in ('time', 'x', 'y', 'rotation', 'scale', 'opacity')]
            self.node_list.insert('', 'end', iid=str(index), values=values + [EASING_NAMES[node['easing']]])
            if select_time is not None and node['time'] == select_time:
                self.selected_index = index
        if self.selected_index is not None:
            key = str(self.selected_index); self.node_list.selection_set(key); self.node_list.see(key)
            self._load_node(self.nodes[self.selected_index])

    def _load_node(self, node):
        self._loading = True
        try:
            for key, variable in self.node_vars.items():
                variable.set(format(node[key], '.9g'))
            self.easing.set(EASING_NAMES[node['easing']])
            self.cursor_time = node['time']; self.cursor_label.set('当前时间 %g 秒' % self.cursor_time)
            self.draft_dirty = False
        finally:
            self._loading = False

    def select_node(self, unused=None):
        selected = self.node_list.selection()
        if not selected:
            return
        index = int(selected[0])
        if index < len(self.nodes):
            self.selected_index = index; self._load_node(self.nodes[index]); self.refresh()

    def _replace_nodes(self, nodes, select_time=None):
        value = dict(duration=self.parameters['duration'].get(), canvas_scale=self.parameters['canvas_scale'].get(), nodes=nodes)
        normalized = ae_animation.normalize(value)
        self.nodes = normalized['nodes']; self.draft_dirty = False
        self._fill_list(select_time); self.refresh()

    def add_node(self):
        try:
            node = self._draft(); self._replace_nodes(self.nodes + [node], float(node['time']))
        except ValueError as error:
            messagebox.showerror('无法新增节点', str(error), parent=self)

    def update_node(self):
        if self.selected_index is None:
            return
        try:
            node = self._draft(); nodes = copy.deepcopy(self.nodes); nodes[self.selected_index] = node
            self._replace_nodes(nodes, float(node['time']))
        except ValueError as error:
            messagebox.showerror('无法更新节点', str(error), parent=self)

    def delete_node(self):
        if self.selected_index is None:
            return
        nodes = copy.deepcopy(self.nodes); del nodes[self.selected_index]
        self.nodes = nodes; self.draft_dirty = False; self._fill_list(); self.refresh()

    def clear_nodes(self):
        self.nodes = []; self.selected_index = None; self._load_node(ae_animation.DEFAULT_NODE)
        self._fill_list(); self.refresh()

    def example(self):
        duration = min(2.0, 128 / self.fps)
        self.parameters['duration'].set(format(duration, '.9g')); self.parameters['canvas_scale'].set('2')
        nodes = [dict(ae_animation.DEFAULT_NODE, time=time, x=x, easing='smooth')
                 for time, x in ((0.0, -20.0), (duration / 2.0, 20.0), (duration, -20.0))]
        self._replace_nodes(nodes, 0.0)

    def draw_timeline(self):
        if not hasattr(self, 'timeline'):
            return
        try:
            duration = float(self.parameters['duration'].get())
            if not math.isfinite(duration) or duration <= 0:
                return
        except (ValueError, TypeError):
            return
        canvas = self.timeline; canvas.delete('all'); width = max(200, canvas.winfo_width())
        left, right, y = 18, width - 18, 23
        canvas.create_line(left, y, right, y, fill='#9aafc3', width=2)
        for index in range(5):
            x = left + (right - left) * index / 4
            canvas.create_line(x, y - 3, x, y + 5, fill='#9aafc3')
            canvas.create_text(x, 46, text='%g' % (duration * index / 4), fill='#52677b', font=('Microsoft YaHei UI', 9))
        for index, node in enumerate(self.nodes):
            x = left + (right - left) * min(1.0, max(0.0, node['time'] / duration))
            canvas.create_polygon(x, y - 7, x + 7, y, x, y + 7, x - 7, y,
                                  fill='#dfab38' if index == self.selected_index else '#1674ce', outline='')
        x = left + (right - left) * min(1.0, max(0.0, self.cursor_time / duration))
        canvas.create_line(x, 3, x, 34, fill='#a52f47', dash=(3, 2))

    def click_timeline(self, event):
        try:
            config = self.collect()
        except ValueError:
            return
        width = max(200, self.timeline.winfo_width()); span = width - 36
        nearest = min(range(len(self.nodes)), key=lambda i: abs(18 + span * self.nodes[i]['time'] / config['duration'] - event.x), default=None)
        if nearest is not None and abs(18 + span * self.nodes[nearest]['time'] / config['duration'] - event.x) <= 10:
            self.node_list.selection_set(str(nearest)); self.node_list.see(str(nearest)); self.select_node(); return
        time = min(config['duration'], max(0.0, (event.x - 18) / span * config['duration']))
        self.node_list.selection_remove(*self.node_list.selection()); self.selected_index = None
        node = dict(ae_animation.DEFAULT_NODE, **ae_animation.sample(config, time)); node['time'] = min(config['duration'], round(time, 6))
        self._load_node(node); self.refresh()

    def _ready_action(self):
        if self.draft_dirty:
            raise ValueError('节点字段有未保存的修改，请先点击“新增节点”或“更新节点”。')
        return self._validated()[0]

    def preview(self):
        if not self.on_preview:
            return
        try:
            self.on_preview(copy.deepcopy(self._ready_action()))
        except (ValueError, OSError, tk.TclError) as error:
            messagebox.showerror('无法预览动画', str(error), parent=self)

    def apply(self):
        try:
            result = self._ready_action(); self.on_apply(copy.deepcopy(result))
        except (ValueError, OSError, tk.TclError) as error:
            messagebox.showerror('无法应用动画', str(error), parent=self); return
        self.destroy()
