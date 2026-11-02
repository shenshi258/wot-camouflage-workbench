"""Light editor layout; visual states are shared with the other workbench windows."""
import tkinter as tk
from tkinter import ttk
from . import light_help, APP_NAME
from .ui_theme import configure_theme, build_header, register_widget, BG, CARD, INK, MUTED, ACCENT


def build_interface(app):
    configure_theme(app)
    variables={str(var):name for var,name in [(app.source,'原始涂装'),(app.client,'游戏目录'),
        (app.effect_mode,'效果模式'),(app.direction,'流水方向'),(app.colors,'颜色顺序'),
        (app.step,'每色秒数'),(app.breath,'呼吸周期'),(app.peak,'峰值倍率'),
        (app.low,'暗相系数'),(app.delay,'每米延迟'),(app.duty,'亮灯比例'),(app.title_value,'作品名称')]}

    def frame(parent, **kw):
        return ttk.Frame(parent, style='Card.TFrame', **kw)

    def label(parent, text, style='TLabel', **kw):
        widget=ttk.Label(parent, text=text, style=style, **kw)
        if text in light_help.TEXT:app.hint(widget,text)
        return widget

    def button(parent, text, command, accent=False):
        widget = app.button(parent, text, command)
        if accent:
            widget.configure(style='Accent.TButton')
        return widget

    def entry(parent, variable, **kw):
        widget = ttk.Entry(parent, textvariable=variable, **kw)
        app.widgets.append(widget)
        app.hint(widget,variables[str(variable)])
        return widget

    def combo(parent, variable, values, **kw):
        widget = ttk.Combobox(parent, textvariable=variable, values=values, state='readonly', **kw)
        app.widgets.append(widget)
        name=variables[str(variable)]
        def current(event):
            return light_help.option(name,variable.get(),app) if name in ('预设','效果模式','流水方向') else light_help.topic(name)
        app.hover_help.attach_combobox(widget,current,lambda value:light_help.option(name,value,app))
        return widget

    header = build_header(app,'灯效制作  ·  导入涂装 → 选择灯面 → 调整光效 → 生成涂装包')
    header.pack(fill='x')

    outer = ttk.Frame(app, style='Backdrop.TFrame', padding=(18, 12, 18, 12))
    outer.pack(fill='both', expand=True)
    inputs = frame(outer, padding=(14, 10))
    inputs.configure(style='Panel.TFrame')
    inputs.pack(fill='x', pady=(0, 10))
    inputs.columnconfigure(1, weight=1)
    label(inputs, '原始涂装', 'Muted.TLabel').grid(row=0, column=0, sticky='w', padx=(0, 12))
    entry(inputs, app.source).grid(row=0, column=1, sticky='ew', padx=(0, 8))
    button(inputs, '导入涂装 / 成品', app.choose_source).grid(row=0, column=2, padx=(0, 6))
    button(inputs, '打开工程', app.open_project).grid(row=0, column=3)
    label(inputs, '游戏目录', 'Muted.TLabel').grid(row=1, column=0, sticky='w', pady=(7, 0))
    entry(inputs, app.client).grid(row=1, column=1, sticky='ew', padx=(0, 8), pady=(7, 0))
    button(inputs, '选择目录', app.choose_client).grid(row=1, column=2, sticky='ew', padx=(0, 6), pady=(7, 0))
    app.check = ttk.Checkbutton(inputs, text='已确认原版正常运行', variable=app.baseline)
    app.check.grid(row=1, column=3, sticky='w', pady=(7, 0))
    app.widgets.append(app.check)
    app.hint(app.check,'已确认原版正常运行')
    app.recovery_hint=label(inputs, '成品恢复：可修改颜色、亮度、节奏并另存工程。未勾选的恢复模型保留原效果；原灯面分组和中和前颜色不能完整找回。', 'Muted.TLabel')
    app.recovery_hint.configure(wraplength=1060)
    app.recovery_hint.grid(row=2,column=0,columnspan=4,sticky='w',pady=(8,0))
    app.hint(app.recovery_hint,'成品恢复说明')
    app.recovery_hint.grid_remove()

    footer = frame(outer, padding=(14, 10))
    footer.configure(style='Panel.TFrame')
    footer.pack(side='bottom', fill='x', pady=(10, 0))
    actions = frame(footer)
    actions.pack(fill='x')
    app.build_button=button(actions, '生成涂装包', app.build, accent=True)
    app.build_button.pack(side='left')
    app.save_button=button(actions, '保存工程', app.save_project)
    app.save_button.pack(side='left', padx=8)
    button(actions, '打开产物', app.show_output).pack(side='left')
    menu_button = ttk.Menubutton(actions, text='安装与日志', direction='above')
    menu_button.pack(side='right')
    app.widgets.append(menu_button)
    app.hint(menu_button,'安装与日志 ▾')
    menu = tk.Menu(menu_button, tearoff=False, font=('Microsoft YaHei UI', 10))
    register_widget(menu,'menu')
    for text, command in [('安装已有灯效包', app.install_existing), ('恢复上次安装', app.restore_previous),
                          ('标记测试开始', app.mark_test), ('提取游戏报错日志', app.export_game_logs),
                          ('选择日志文件提取', app.export_selected_logs)]:
        menu.add_command(label=text, command=command)
    menu.add_separator()
    menu.add_checkbutton(label='优先提取测试标记后的日志', variable=app.log_since_mark)
    menu_button.configure(menu=menu)
    app.install_menu=menu
    app.hover_help.attach_menu(menu,light_help.topic)
    auto = ttk.Checkbutton(actions, text='生成后自动安装', variable=app.auto_install)
    auto.pack(side='right', padx=12)
    app.widgets.append(auto)
    app.hint(auto,'生成后自动安装')
    packaging=frame(footer);packaging.pack(fill='x',pady=(10,0))
    label(packaging,'自动打包','Section.TLabel').pack(side='left',padx=(0,14))
    app.bundle_check=ttk.Checkbutton(packaging,text='生成后自动打包 ZIP',variable=app.auto_bundle)
    app.bundle_check.pack(side='left');app.widgets.append(app.bundle_check)
    app.hover_help.attach(app.bundle_check,lambda e:light_help.Help('自动打包 ZIP','生成并核对安装包后，将 .wotmod、使用说明和验证记录压入 ZIP。ZIP 不是安装位置；不会自动安装。'))
    embed=ttk.Checkbutton(packaging,text='嵌入可恢复工程',variable=app.embed_recoverable)
    embed.pack(side='left',padx=18);app.embed_check=embed;app.widgets.append(embed);app.hint(embed,'嵌入可恢复工程')
    destination=frame(footer);destination.pack(fill='x',pady=(6,0))
    label(destination,'保存位置','Muted.TLabel').pack(side='left',padx=(0,12))
    ttk.Entry(destination,textvariable=app.output_folder,state='readonly').pack(side='left',fill='x',expand=True)
    button(destination,'更改目录',app.choose_output_folder).pack(side='left',padx=(8,0))
    backup_row=frame(footer);backup_row.pack(fill='x',pady=(7,0))
    label(backup_row,'工程工具','Muted.TLabel').pack(side='left',padx=(0,10))
    ttk.Checkbutton(backup_row,text='每 5 分钟自动保存灯效工程',variable=app.auto_save,command=app.change_autosave).pack(side='left')
    ttk.Button(backup_row,text='恢复自动保存工程',command=app.restore_autosave).pack(side='left',padx=8)
    button(backup_row,'合并同车灯效包',app.merge_packages).pack(side='left',padx=8)
    status = frame(footer)
    status.pack(fill='x', pady=(8, 0))
    app.progress = ttk.Progressbar(status, mode='determinate', length=90)
    app.progress.pack(side='left', padx=(0, 10))
    app.hint(app.progress,'进度')
    app.status_label = ttk.Label(status, textvariable=app.status, style='Muted.TLabel', wraplength=1000)
    app.status_label.pack(side='left', fill='x', expand=True)
    app.hint(app.status_label,'状态')
    status.bind('<Configure>', lambda e: app.status_label.configure(wraplength=max(300, e.width-110)))

    body = ttk.Panedwindow(outer, orient='horizontal')
    body.pack(fill='both', expand=True)
    left = frame(body, padding=12, width=350)
    right_panel = frame(body, padding=12)
    left.configure(style='Panel.TFrame');right_panel.configure(style='Panel.TFrame')
    body.add(left, weight=1)
    body.add(right_panel, weight=3)

    # The editor needs more vertical room than a small laptop window provides.
    # Scroll its content as a whole instead of silently clipping the controls;
    # at larger sizes the preview grows to fill the available space.
    viewport=tk.Canvas(right_panel,bg=CARD,highlightthickness=0,borderwidth=0)
    register_widget(viewport,'surface')
    right_scroll=ttk.Scrollbar(right_panel,orient='vertical',command=viewport.yview)
    viewport.configure(yscrollcommand=right_scroll.set)
    right_scroll.pack(side='right',fill='y');viewport.pack(side='left',fill='both',expand=True)
    right=frame(viewport)
    window=viewport.create_window((0,0),window=right,anchor='nw')
    def fit_editor(event=None):
        width=max(1,viewport.winfo_width())
        height=max(viewport.winfo_height(),right.winfo_reqheight())
        viewport.itemconfigure(window,width=width,height=height)
        viewport.configure(scrollregion=(0,0,width,height))
    viewport.bind('<Configure>',fit_editor)
    right.bind('<Configure>',fit_editor)
    app.editor_viewport=viewport
    app.editor_scroll=right_scroll
    app.hover_help.attach(right_scroll,lambda event:light_help.Help('编辑区滚动',
        '窗口较小时，滚动右侧编辑区可查看预览、套选工具和完整光效参数。'))
    # Reserve the editor and its controls before the expandable preview.
    editor=frame(right)
    editor.pack(side='bottom',fill='x',pady=(8,0))
    preview_tools=frame(right)
    preview_tools.pack(side='bottom',fill='x')
    label(left, '灯面资料库', 'Section.TLabel').pack(anchor='w')
    label(left, '勾选决定生成范围，套选用于批量操作。', 'Muted.TLabel').pack(anchor='w', pady=(3, 10))
    row = frame(left)
    row.pack(fill='x', pady=(0, 8))
    button(row, '全选可制作', lambda: app.select_all(True)).pack(side='left')
    button(row, '清空', lambda: app.select_all(False)).pack(side='left', padx=5)
    button(row, '勾选 / 取消', app.toggle_current).pack(side='left')
    table = frame(left)
    table.pack(fill='both', expand=True)
    app.tree = ttk.Treeview(table, columns=('state', 'anchor', 'count'), show='tree headings', selectmode='extended')
    app.tree.heading('#0', text='车型 / 灯面')
    app.tree.column('#0', width=160, minwidth=90)
    for name, title, width in [('state', '状态', 54), ('anchor', '挂点', 54), ('count', '面数', 46)]:
        app.tree.heading(name, text=title)
        app.tree.column(name, width=width, minwidth=40, stretch=False)
    app.tree.tag_configure('unsupported', foreground='#9caab5')
    scroll = ttk.Scrollbar(table, orient='vertical', command=app.tree.yview)
    app.tree.configure(yscrollcommand=scroll.set)
    app.tree.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    app.tree.bind('<<TreeviewSelect>>', app.on_pick)
    app.tree.bind('<Double-1>', lambda e: app.toggle_current())
    app.tree.bind('<space>', lambda e: (app.toggle_current(), 'break')[1])
    app.hover_help.attach(app.tree,app.tree_help)
    app.hint(scroll,'灯面滚动条')
    app.count_label = label(left, '等待提取灯面', 'Muted.TLabel')
    app.count_label.pack(anchor='w', pady=(8, 0))
    app.hint(app.count_label,'灯面资料库')
    app.scan_issue_button=button(left,'查看资源问题',app.show_scan_issues)
    app.scan_issue_button.pack(anchor='w',pady=(4,0));app.scan_issue_button.state(['disabled'])
    # Reserve the library footer before the expandable tree. At a smaller
    # height, pack otherwise clips this button down to an empty thin strip.
    app.scan_issue_button.pack_forget();app.count_label.pack_forget();table.pack_forget()
    app.scan_issue_button.pack(side='bottom',anchor='w',pady=(4,0))
    app.count_label.pack(side='bottom',anchor='w',pady=(8,0))
    table.pack(side='top',fill='both',expand=True)

    head = frame(right)
    head.pack(fill='x')
    variables[str(app.preview_mode)]='预览模式'
    mode=combo(head,app.preview_mode,('位置示意','实时灯效'),width=9)
    mode.pack(side='left');mode.bind('<<ComboboxSelected>>',app.change_preview_mode)
    button(head,'三维实时预览',app.open_preview3d,accent=True).pack(side='left',padx=(8,0))
    variables[str(app.performance)]='性能档'
    combo(head,app.performance,app.performance_profiles,width=6).pack(side='left',padx=(6,0))
    secondary=frame(right);secondary.pack(fill='x',pady=(5,0))
    app.preview_scope = tk.StringVar(value='当前模型')
    variables[str(app.preview_scope)]='预览范围'
    scope = combo(head, app.preview_scope, ('当前模型', '全部灯面'), width=9)
    scope.pack(side='right')
    scope.bind('<<ComboboxSelected>>', lambda e: app.reset_preview())
    label(head, '预览范围', 'Muted.TLabel').pack(side='right', padx=8)
    zoom_row=frame(secondary);zoom_row.pack(side='left')
    button(zoom_row,'适应',app.reset_preview).pack(side='right')
    button(zoom_row,'＋',lambda:app.zoom_preview(1.25)).pack(side='right',padx=4)
    zoom_label=ttk.Label(zoom_row,textvariable=app.zoom_text,width=6,anchor='center')
    zoom_label.pack(side='right');app.hint(zoom_label,'缩放比例')
    button(zoom_row,'−',lambda:app.zoom_preview(.8)).pack(side='right')
    app.canvas = tk.Canvas(right, height=170, bg='#f7f9fc', highlightthickness=1, highlightbackground='#edf0f4', cursor='crosshair')
    app.canvas.pack(fill='both', expand=True, pady=(8, 5))
    app.canvas.bind('<Configure>', lambda e: app.draw_preview())
    app.canvas.bind('<Button-1>', app.on_canvas_press)
    app.canvas.bind('<B1-Motion>', app.on_canvas_drag)
    app.canvas.bind('<ButtonRelease-1>', app.on_canvas_release)
    app.canvas.bind('<MouseWheel>',app.on_preview_wheel)
    app.canvas.bind('<Button-2>',app.on_pan_press)
    app.canvas.bind('<B2-Motion>',app.on_pan_drag)
    app.canvas.bind('<ButtonRelease-2>',app.on_pan_release)
    app.hint(app.canvas,'位置预览')
    app.detail = tk.StringVar()
    app.detail_label = ttk.Label(right, textvariable=app.detail, style='Muted.TLabel', wraplength=650)
    app.hint(app.detail_label,'灯面资料库')
    app.canvas.bind('<Configure>', lambda e: app.detail_label.configure(wraplength=max(250, e.width-8)), add='+')
    label(secondary,'向下滚动编辑配方','Muted.TLabel').pack(side='right',padx=(4,0))
    live_row=frame(secondary);live_row.pack(side='left',padx=(10,0))
    play=button(live_row,'暂停',app.pause_live);play.configure(textvariable=app.live_play_text)
    play.pack(side='right')
    button(live_row,'重播',app.restart_live).pack(side='right',padx=4)
    row = frame(preview_tools)
    row.pack(fill='x', pady=(3, 4))
    picked_label=ttk.Label(row, textvariable=app.pick_text, style='Muted.TLabel');picked_label.pack(side='left')
    app.hint(picked_label,'套选统计')
    button(row, '清除', app.pick_clear).pack(side='right')
    button(row, '整模型扩选', app.pick_models).pack(side='right', padx=4)
    button(row, '全选范围', app.pick_scope_all).pack(side='right')
    row = frame(preview_tools)
    row.pack(fill='x', pady=(0, 6))
    button(row, '勾选套选', lambda: app.mark_picked(True)).pack(side='left')
    button(row, '取消勾选', lambda: app.mark_picked(False)).pack(side='left', padx=4)
    button(row, '只保留套选', app.keep_only_picked).pack(side='left')
    caption=ttk.Label(row,textvariable=app.preview_caption,style='Muted.TLabel',width=31,anchor='e')
    caption.pack(side='right')
    app.hover_help.attach(caption,lambda e:light_help.Help('预览说明',app.live_note.get()+'\n\n'+light_help.TEXT['实时灯效'])
                          if app.preview_mode.get()=='实时灯效' else light_help.topic('位置预览'))

    ttk.Separator(editor).pack(fill='x', pady=(2, 8))
    head = frame(editor)
    head.pack(fill='x')
    label(head, '光效设置', 'Section.TLabel').pack(side='left')
    for value in ('套选灯面', '套选模型', '全局配方'):
        radio = ttk.Radiobutton(head, text=value, variable=app.edit_scope, value=value,
                                command=app.change_edit_scope, style='Scope.TRadiobutton')
        radio.pack(side='right', padx=(4, 0))
        app.widgets.append(radio)
        app.hint(radio,value)
    button(head, '放弃草稿修改', app.discard_recipe_draft).pack(side='right', padx=(4, 8))
    editor_label=ttk.Label(editor, textvariable=app.editor_hint, style='Muted.TLabel');editor_label.pack(anchor='w',pady=(4,6))
    app.hint(editor_label,'配方编辑范围')

    form = frame(editor)
    form.pack(fill='x')
    form.columnconfigure(1, weight=1)
    form.columnconfigure(3, weight=1)
    app.preset = tk.StringVar(value='蓝粉黄流水呼吸')
    variables[str(app.preset)]='预设'
    row = frame(form)
    row.grid(row=0, column=0, columnspan=4, sticky='ew', pady=(0, 6))
    label(row, '预设', 'Muted.TLabel').pack(side='left', padx=(0, 10))
    app.preset_combo = combo(row, app.preset, list(app.preset_library), width=14)
    app.preset_combo.pack(side='left', fill='x', expand=True)
    app.preset_combo.bind('<<ComboboxSelected>>', app.apply_preset)
    button(row, '存为预设', app.save_current_preset).pack(side='left', padx=5)
    button(row, '管理', app.manage_presets).pack(side='left')
    app.dimming_check=ttk.Checkbutton(row,text='明暗变化',variable=app.dimming)
    app.dimming_check.pack(side='left',padx=(10,0))
    app.widgets.append(app.dimming_check);app.hint(app.dimming_check,'明暗变化')
    label(form, '效果模式', 'Muted.TLabel').grid(row=1, column=0, sticky='w', padx=(0, 10))
    combo(form, app.effect_mode, app.engine_modes, width=10).grid(row=1, column=1, sticky='ew', pady=3)
    label(form, '流水方向', 'Muted.TLabel').grid(row=1, column=2, sticky='w', padx=(14, 8))
    combo(form, app.direction, app.engine_directions, width=10).grid(row=1, column=3, sticky='ew', pady=3)
    direction_card=frame(form);direction_card.grid(row=2,column=0,columnspan=4,sticky='ew',pady=(6,8))
    app.direction_buttons=[]
    choices=[('↑ 向上','向上'),('↓ 向下','向下'),('← 向左','向左'),('→ 向右','向右'),
             ('↖ 偏左上','偏左上'),('↗ 偏右上','偏右上'),('↙ 偏左下','偏左下'),('↘ 偏右下','偏右下')]
    for i,(text,value) in enumerate(choices):
        w=ttk.Radiobutton(direction_card,text=text,value=value,variable=app.direction,style='Scope.TRadiobutton')
        w.grid(row=i//4,column=i%4,sticky='ew',padx=3,pady=3);direction_card.columnconfigure(i%4,weight=1)
        app.widgets.append(w);app.direction_buttons.append((value,w))
        app.hover_help.attach(w,lambda e,v=value:light_help.option('流水方向',v,app))
    label(form, '颜色顺序', 'Muted.TLabel').grid(row=3, column=0, sticky='w',padx=(0,10))
    colors_row=frame(form)
    colors_row.grid(row=3, column=1, columnspan=3, sticky='ew', pady=3)
    button(colors_row,'调色盘',app.open_palette).pack(side='right',padx=(8,0))
    variables[str(app.color_curve)]='换色曲线'
    combo(colors_row,app.color_curve,('柔和','匀速无缝'),width=7).pack(side='right',padx=(4,0))
    label(colors_row,'换色', 'Muted.TLabel').pack(side='right',padx=(8,0))
    entry(colors_row, app.colors).pack(side='left',fill='x',expand=True)
    numbers = frame(form)
    numbers.grid(row=4, column=0, columnspan=4, sticky='ew', pady=(3, 4))
    pairs = [('每色秒数', app.step), ('呼吸周期', app.breath), ('峰值倍率', app.peak),
             ('暗相系数', app.low), ('每米延迟', app.delay), ('亮灯比例', app.duty)]
    app.parameter_entries={}
    for index, (text, variable) in enumerate(pairs):
        label(numbers, text, 'Muted.TLabel').grid(row=0, column=index, sticky='w', padx=(0, 8))
        field=entry(numbers, variable, width=6);field.grid(row=1, column=index, sticky='ew', padx=(0, 8), pady=(3, 0))
        app.parameter_entries[text]=field
        numbers.columnconfigure(index, weight=1, uniform='recipe')
    row = frame(form)
    row.grid(row=5, column=0, columnspan=4, sticky='ew', pady=(3, 0))
    label(row, '作品名称', 'Muted.TLabel').pack(side='left', padx=(0, 10))
    entry(row, app.title_value, width=12).pack(side='left', fill='x', expand=True)
    # Keep the name and four recipe actions on separate rows so none are
    # clipped when the editor is narrow.
    row = frame(form)
    row.grid(row=6, column=0, columnspan=4, sticky='ew', pady=(5, 0))
    app.read_recipe_button=button(row, '读取套选配方', app.load_picked_recipe)
    app.read_recipe_button.pack(side='left', padx=5)
    app.apply_button=ttk.Button(row,text='应用到套选模型',command=app.apply_recipe_to_picked,style='Accent.TButton')
    app.widgets.append(app.apply_button)
    app.hover_help.attach(app.apply_button,lambda e:light_help.topic('应用到套选灯面' if app.edit_scope.get()=='套选灯面' else '应用到套选模型'))
    app.apply_button.pack(side='left')
    app.restore_recipe_button=button(row, '恢复全局', app.clear_recipe_on_picked)
    app.restore_recipe_button.pack(side='left', padx=(5, 0))
    app.clear_all_button=button(row, '全部改回全局', app.clear_all_recipe_overrides)
    app.hover_help.attach(app.clear_all_button,lambda e:light_help.topic('全部改回全局'))
    app.clear_all_button.pack(side='left', padx=(5, 0))

    def scroll_editor(event):
        if viewport.winfo_reqheight()<=0:return None
        viewport.yview_scroll(-int(event.delta/120) or (-1 if event.delta>0 else 1),'units')
        return 'break'
    def bind_editor_wheel(widget):
        if widget is app.canvas:return
        widget.bind('<MouseWheel>',scroll_editor,add='+')
        for child in widget.winfo_children():bind_editor_wheel(child)
    bind_editor_wheel(right)
