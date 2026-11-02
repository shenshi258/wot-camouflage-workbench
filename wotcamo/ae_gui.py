"""Desktop authoring window for AE-exported transparent PNG animations."""
import argparse,copy,os,queue,subprocess,sys,tempfile,threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog,colorchooser
from .common import ROOT
from . import ae_effects as ae,ae_presets,ae_help,preview3d,APP_NAME
from .light_tooltips import HoverHelp
from .ui_theme import configure_theme, build_header, prepare_dialog, style_listbox, register_widget, lock_controls, unlock_controls, start_progress, stop_progress

PARTS={'车体':'hull','炮塔':'turret','炮管（随俯仰）':'gun'}
PLANES={'自动贴合':'auto','侧面':'side','正面':'front','顶面':'top'}
PLACEMENTS={'独立平面':'plane','贴面播放':'surface','贴面发光':'surface_glow'}
BLENDS={'发光叠加':'add','普通透明':'alpha'}

def _preset_action_buttons(parent,actions):
    """Two rows keep all six actions accessible at the 700px dialog minimum."""
    for column in range(3):parent.columnconfigure(column,weight=1,uniform='preset_actions',minsize=120)
    buttons=[]
    for index,(label,command) in enumerate(actions):
        row,column=divmod(index,3)
        button=ttk.Button(parent,text=label,command=command)
        button.grid(row=row,column=column,sticky='ew',padx=(0,7) if column<2 else 0,pady=(0,7) if row==0 else 0)
        buttons.append(button)
    return buttons

class AEImporter(tk.Tk):
    def __init__(self,source='',client=''):
        super().__init__();self.title(APP_NAME+' · AE 特效导入');self.geometry('1120x800');self.minsize(1020,700)
        self.option_add('*Font',('Microsoft YaHei UI',10));self.configure(bg='#f5f5f7')
        self.project=None;self.loaded_source=None;self.clip=None;self.session=None;self.busy=False;self.buttons=[];self.events=queue.Queue();self.pending=None;self.closing=False
        (ROOT/'.cache').mkdir(exist_ok=True);self.work=Path(tempfile.mkdtemp(prefix='ae_import_',dir=ROOT/'.cache'))
        self.source=tk.StringVar(value=source);self.client=tk.StringVar(value=client);self.baseline=tk.BooleanVar(value=False)
        self.title_value=tk.StringVar(value='我的AE特效');self.premult=tk.BooleanVar(value=False)
        self.columns=tk.StringVar(value='4');self.rows=tk.StringVar(value='4');self.count=tk.StringVar(value='16')
        self.note=tk.StringVar(value='选择涂装包，再导入 AE 导出的透明 PNG 素材。')
        self.clip_note=tk.StringVar(value='尚未导入素材');self.client_note=tk.StringVar()
        self.values={k:tk.StringVar(value=str(v)) for k,v in ae.DEFAULTS.items() if k not in ('part','plane','mirror','blend','placement')}
        self.part=tk.StringVar(value='车体');self.plane=tk.StringVar(value='侧面');self.blend=tk.StringVar(value='发光叠加');self.mirror=tk.BooleanVar(value=False)
        self.placement=tk.StringVar(value='独立平面');self.mode_note=tk.StringVar()
        self.selection_note=tk.StringVar(value='尚未选择承载面')
        self.auto_bundle=tk.BooleanVar(value=True);self.include_project=tk.BooleanVar(value=True)
        self.output_folder=tk.StringVar(value=str(ROOT/'result/AE特效'));self.last_output=None
        self.live_worker=False;self.live_again=False
        self._busy_controls=[]
        self.hover_help=HoverHelp(self)
        self.preset_name=tk.StringVar();self.preset_note=tk.StringVar();self.preset_records=[]
        self.interface()
        self.attach_explanations(self)
        self.refresh_presets()
        for var in list(self.values.values())+[self.part,self.plane,self.blend,self.mirror]:var.trace_add('write',self.changed)
        self.placement.trace_add('write',self.mode_changed)
        self.mode_changed()
        self.poll_id=self.after(150,self.poll);self.protocol('WM_DELETE_WINDOW',self.close)
        if client:self.check_client()

    def interface(self):
        """Source left, fitting right, fixed actions below: no long stacked form."""
        configure_theme(self)
        box=ttk.Frame(self,padding=18,style='Backdrop.TFrame');box.pack(fill='both',expand=True)
        header=build_header(box,'AE 特效  ·  选择涂装 → 套用/导入 → 吸附装甲 → 生成涂装包');header.pack(fill='x',pady=(0,12))
        self.button(header.actions,'打开 AE 工程…',self.load).pack(side='right',padx=(8,0))
        self.button(header.actions,'保存 AE 工程…',self.save).pack(side='right')
        preset_box=ttk.LabelFrame(box,text='AE 特效预设',padding=(12,8));preset_box.pack(fill='x',pady=(0,12))
        preset_row=ttk.Frame(preset_box);preset_row.pack(fill='x')
        self.preset_combo=ttk.Combobox(preset_row,textvariable=self.preset_name,state='readonly',width=26)
        self.preset_combo.pack(side='left',fill='x',expand=True)
        self.preset_apply=self.button(preset_row,'套用',self.apply_preset);self.preset_apply.pack(side='left',padx=8)
        self.button(preset_row,'保存为预设…',self.save_preset).pack(side='left')
        self.button(preset_row,'管理 / 导入…',self.manage_presets).pack(side='left',padx=(8,0))
        self.preset_combo.bind('<<ComboboxSelected>>',self.describe_preset)
        ttk.Label(preset_box,textvariable=self.preset_note,wraplength=1010,style='Muted.TLabel').pack(anchor='w',pady=(6,0))
        # Pack the action/footer first so it cannot disappear on a smaller screen.
        footer=ttk.Frame(box,padding=12,style='Panel.TFrame');footer.pack(side='bottom',fill='x',pady=(12,0))
        self.progress=ttk.Progressbar(footer,mode='determinate');self.progress.pack(fill='x',pady=(0,10))
        actions=ttk.Frame(footer);actions.pack(fill='x')
        ttk.Label(actions,text='成品名称').pack(side='left');ttk.Entry(actions,textvariable=self.title_value,width=23).pack(side='left',padx=10)
        self.export_button=self.button(actions,'生成涂装包',self.export);self.export_button.configure(style='Accent.TButton');self.export_button.pack(side='right')
        self.button(actions,'打开三维预览',self.preview).pack(side='right',padx=8)
        packaging=ttk.Frame(footer);packaging.pack(fill='x',pady=(9,0))
        ttk.Checkbutton(packaging,text='生成后自动打包 ZIP',variable=self.auto_bundle,command=self.update_packaging).pack(side='left')
        self.project_toggle=ttk.Checkbutton(packaging,text='附带可编辑 AE 工程',variable=self.include_project);self.project_toggle.pack(side='left',padx=14)
        ttk.Label(packaging,text='随 ZIP 附带本次特效预设',style='Muted.TLabel').pack(side='left')
        self.button(packaging,'打开成品目录',self.open_results).pack(side='right')
        ttk.Label(footer,text=ae.PACKAGE_CONFLICT_NOTE,style='Muted.TLabel',wraplength=1020).pack(anchor='w',pady=(6,0))
        folder=ttk.Frame(footer);folder.pack(fill='x',pady=(7,0));ttk.Label(folder,text='保存位置').pack(side='left')
        ttk.Entry(folder,textvariable=self.output_folder,state='readonly').pack(side='left',fill='x',expand=True,padx=10);self.button(folder,'更改目录',self.choose_output_folder).pack(side='right')
        ttk.Label(footer,textvariable=self.note,wraplength=1020,foreground='#44516a').pack(anchor='w',pady=(9,0))
        body=ttk.Frame(box,style='Backdrop.TFrame');body.pack(fill='both',expand=True);body.columnconfigure(0,weight=0,minsize=365);body.columnconfigure(1,weight=1);body.rowconfigure(0,weight=1)
        left=ttk.LabelFrame(body,text='1  涂装与素材',padding=14);left.grid(row=0,column=0,sticky='nsew',padx=(0,15))
        left_canvas=tk.Canvas(left,highlightthickness=0,bg='#ffffff');left_scroll=ttk.Scrollbar(left,orient='vertical',command=left_canvas.yview);left_canvas.configure(yscrollcommand=left_scroll.set)
        register_widget(left_canvas,'surface')
        left_scroll.pack(side='right',fill='y');left_canvas.pack(side='left',fill='both',expand=True)
        left=ttk.Frame(left_canvas,padding=(0,0,5,10));left_item=left_canvas.create_window((0,0),window=left,anchor='nw')
        left.bind('<Configure>',lambda e:left_canvas.configure(scrollregion=left_canvas.bbox('all')));left_canvas.bind('<Configure>',lambda e:left_canvas.itemconfigure(left_item,width=e.width))
        self.bind('<MouseWheel>',lambda e:left_canvas.yview_scroll(int(-e.delta/120),'units') if str(e.widget).startswith(str(left)) else None,add='+')
        for label,var,command in [('涂装包',self.source,self.choose_source),('实际游戏目录',self.client,self.choose_client)]:
            ttk.Label(left,text=label).pack(anchor='w',pady=(0,5));row=ttk.Frame(left);row.pack(fill='x',pady=(0,11))
            ttk.Entry(row,textvariable=var,state='readonly',width=27).pack(side='left',fill='x',expand=True);self.button(row,'选择',command).pack(side='left',padx=(6,0))
        ttk.Label(left,textvariable=self.client_note,foreground='#58657a',wraplength=325).pack(anchor='w')
        ttk.Checkbutton(left,text='我确认原涂装在所选客户端\n可以正常显示',variable=self.baseline).pack(anchor='w',pady=(8,15))
        ttk.Separator(left).pack(fill='x',pady=(0,12));ttk.Label(left,text='AE 导出的透明 PNG',font=('Microsoft YaHei UI',11,'bold')).pack(anchor='w')
        row=ttk.Frame(left);row.pack(fill='x',pady=10)
        self.button(row,'导入序列帧…',self.choose_frames).pack(side='left',fill='x',expand=True);self.button(row,'选择帧文件夹…',self.choose_folder).pack(side='left',fill='x',expand=True,padx=(7,0))
        self.button(left,'导入 PNG 图集…',self.choose_sheet).pack(fill='x')
        row=ttk.Frame(left);row.pack(fill='x',pady=9)
        for label,var in [('列',self.columns),('行',self.rows),('帧数',self.count)]:
            ttk.Label(row,text=label).pack(side='left',padx=(0,4));ttk.Entry(row,textvariable=var,width=5).pack(side='left',padx=(0,10))
        ttk.Checkbutton(left,text='素材为黑底预乘 Alpha',variable=self.premult).pack(anchor='w',pady=5)
        ttk.Label(left,textvariable=self.clip_note,wraplength=320,foreground='#2266ae').pack(anchor='w',pady=(12,8))
        ttk.Label(left,text='最多 128 帧、1～60 FPS。\n图集按从左到右、从上到下读取。\n建议 AE 导出 RGB＋Alpha / 直通。',wraplength=325,foreground='#58657a').pack(anchor='w',pady=5)
        # The whole right column must remain reachable when the footer and
        # preset header consume most of a compact or high-DPI window.
        right_outer=ttk.Frame(body);right_outer.grid(row=0,column=1,sticky='nsew')
        right_canvas=tk.Canvas(right_outer,highlightthickness=0,bg='#ffffff')
        register_widget(right_canvas,'surface')
        right_scroll=ttk.Scrollbar(right_outer,orient='vertical',command=right_canvas.yview)
        right_canvas.configure(yscrollcommand=right_scroll.set);right_scroll.pack(side='right',fill='y');right_canvas.pack(side='left',fill='both',expand=True)
        right=ttk.Frame(right_canvas);right_item=right_canvas.create_window((0,0),window=right,anchor='nw')
        right.bind('<Configure>',lambda e:right_canvas.configure(scrollregion=right_canvas.bbox('all')))
        right_canvas.bind('<Configure>',lambda e:right_canvas.itemconfigure(right_item,width=e.width))
        def scroll_right(event):
            widget=str(event.widget)
            if widget.startswith(str(right)) and not widget.startswith(str(self.param_tabs)):
                right_canvas.yview_scroll(int(-event.delta/120),'units')
        self.bind('<MouseWheel>',scroll_right,add='+')
        mode=ttk.LabelFrame(right,text='2  选择呈现方式',padding=12);mode.pack(fill='x')
        ttk.Combobox(mode,textvariable=self.placement,values=list(PLACEMENTS),state='readonly',width=20).pack(anchor='w')
        ttk.Checkbutton(mode,text='左右双侧显示（镜像到另一侧）',variable=self.mirror).pack(anchor='w',pady=(7,0))
        ttk.Label(mode,textvariable=self.mode_note,wraplength=590,foreground='#58657a').pack(anchor='w',pady=(8,0))
        selected=ttk.LabelFrame(right,text='承载面',padding=12);selected.pack(fill='x',pady=12)
        ttk.Label(selected,textvariable=self.selection_note,wraplength=590).pack(anchor='w')
        row=ttk.Frame(selected);row.pack(fill='x',pady=(8,0));self.button(row,'新建流动平面',self.new_plane).pack(side='left');self.button(row,'吸附装甲 / 选择承载面',self.snap_preview).pack(side='left',padx=8);self.button(row,'清除承载面',self.clear_surface).pack(side='left')
        ttk.Label(selected,text='“吸附装甲”会自动贴合并以点击处为中心。普通点选或框选后“使用选区”只更新范围，保留当前呈现方式、透明方式和映射方向；需要贴面时再选择呈现方式。',wraplength=590,foreground='#58657a').pack(anchor='w',pady=(7,0))
        self.param_tabs=ttk.Notebook(right);self.param_tabs.pack(fill='both',expand=True)
        def scroll_tab(title):
            outer=ttk.Frame(self.param_tabs);self.param_tabs.add(outer,text=title)
            canvas=tk.Canvas(outer,highlightthickness=0,bg='#ffffff');scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=scroll.set)
            register_widget(canvas,'surface')
            scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True);inner=ttk.Frame(canvas,padding=14);item=canvas.create_window((0,0),window=inner,anchor='nw')
            inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')));canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
            self.bind('<MouseWheel>',lambda e:canvas.yview_scroll(int(-e.delta/120),'units') if str(e.widget).startswith(str(inner)) else None,add='+')
            return inner
        fitting=scroll_tab('长宽与贴合');placement=scroll_tab('独立平面位置');deform=scroll_tab('四角变形');crop=scroll_tab('素材裁剪');play=scroll_tab('播放与透明')
        self.plane_widgets=[];self.surface_widgets=[];self.fields={}
        def choice(parent,label,var,options):
            row=ttk.Frame(parent);row.pack(fill='x',pady=5);ttk.Label(row,text=label,width=16).pack(side='left');w=ttk.Combobox(row,textvariable=var,values=list(options),state='readonly',width=21);w.pack(side='left');return w
        def field(parent,label,key):
            row=ttk.Frame(parent);row.pack(fill='x',pady=4);ttk.Label(row,text=label,width=16).pack(side='left');w=ttk.Entry(row,textvariable=self.values[key],width=13);w.pack(side='left');self.fields[key]=w;return w
        choice(fitting,'映射方向',self.plane,PLANES);field(fitting,'精确方向（度）','angle')
        # Independent axes are shared by every placement mode; only fitting
        # offsets and surface-only controls follow the selected surface mode.
        field(fitting,'长度（横向倍率）','uv_scale_x');field(fitting,'宽度（纵向倍率）','uv_scale_y')
        for label,key in [('贴面整体缩放','uv_scale'),('贴面横向偏移','u_offset'),('贴面纵向偏移','v_offset'),('发光离面距离（米）','lift')]:self.surface_widgets.append(field(fitting,label,key))
        ttk.Label(fitting,text='长度只改横向，宽度只改纵向，1 为原大小；独立平面也可用。贴面若只显示一小块，请在三维勾选“整块装甲”并重新吸附。装甲外侧仍会裁切。',wraplength=550,style='Muted.TLabel').pack(anchor='w',pady=10)
        self.button(fitting,'重置缩放、偏移和裁剪',self.reset_fitting).pack(anchor='w')
        for label,key in [('左侧裁剪（%）','crop_left'),('右侧裁剪（%）','crop_right'),('顶部裁剪（%）','crop_top'),('底部裁剪（%）','crop_bottom')]:field(crop,label,key)
        ttk.Label(crop,text='0 表示不裁剪。分别隐藏每帧的四边，剩余图像保持原位，不拉伸填满。左右、上下的裁剪合计分别须小于 100%。预览和生成包使用相同裁剪结果。',wraplength=550,style='Muted.TLabel').pack(anchor='w',pady=12)
        self.plane_widgets.append(choice(placement,'挂载部件',self.part,PARTS))
        for label,key in [('平面宽度（米）','width'),('横向位置（米）','x'),('上下位置（米）','y'),('前后位置（米）','z')]:self.plane_widgets.append(field(placement,label,key))
        ttk.Label(deform,text='三维中拖动四角、边中点；拖中心或平面可移动。Shift 拖动沿平面法线调整深度，可对齐倾斜装甲。下面可精确输入；变形随预设、工程及涂装包保存。',wraplength=550,style='Muted.TLabel').pack(anchor='w',pady=8)
        for corner,caption in [('tl','左上'),('tr','右上'),('br','右下'),('bl','左下')]:
            for axis,label in [('x','横向'),('y','纵向'),('z','深度')]:self.plane_widgets.append(field(deform,caption+' · '+label,'warp_'+corner+'_'+axis))
        self.button(deform,'重置四角变形',self.reset_deform).pack(anchor='w',pady=8)
        field(play,'播放帧率','fps');field(play,'亮度倍率','brightness');choice(play,'透明方式',self.blend,BLENDS)
        colors=ttk.LabelFrame(play,text='特效颜色',padding=10);colors.pack(fill='x',pady=8)
        field(colors,'颜色（#RRGGBB）','tint_color')
        row=ttk.Frame(colors);row.pack(fill='x',pady=5)
        self.color_swatch=tk.Label(row,width=5,bg='#ffffff',relief='solid',borderwidth=1);self.color_swatch.pack(side='left',padx=(0,8))
        self.button(row,'选择特效颜色…',self.choose_effect_color).pack(side='left')
        self.button(row,'恢复素材原色',lambda:self.values['tint_strength'].set('0')).pack(side='left',padx=8)
        field(colors,'着色强度（%）','tint_strength')
        ttk.Scale(colors,from_=0,to=100,variable=self.values['tint_strength']).pack(fill='x',pady=5)
        row=ttk.Frame(colors);row.pack(fill='x',pady=4)
        for label,color in [('樱粉','#FF85C2'),('冰蓝','#68DFFF'),('紫晶','#B58AFF'),('鎏金','#FFD06B')]:
            self.button(row,label,lambda color=color:self.set_effect_color(color)).pack(side='left',padx=(0,6))
        ttk.Label(colors,text='0% 保留素材原色，100% 改为所选颜色；透明边缘和原有明暗细节保留。亮度单独调节，颜色可随预设保存。',wraplength=520,style='Muted.TLabel').pack(anchor='w',pady=7)
        ttk.Label(play,text='发光叠加适合流星、火焰；普通透明适合烟雾和带遮挡的动画。\n预览和导出共用帧序、尺寸及混合设置，游戏曝光和泛光仍需实测。',wraplength=550,foreground='#58657a').pack(anchor='w',pady=15)

    def mode_changed(self,*args):
        """Mode defaults guide the user; saved projects restore explicit settings afterwards."""
        surface=self.placement.get()!='独立平面';glow=self.placement.get()=='贴面发光'
        self.mode_note.set('按所选模型表面贴合播放，超出选区和图像边界的部分裁掉。' if surface and not glow else '复制所选表面，沿法线抬高后播放发光动画；不改原车材质。' if glow else '动画在独立平面循环播放；拖面移动、拖四角变形，Shift 拖动调深度。')
        if surface:self.plane.set('自动贴合');self.blend.set('发光叠加' if glow else '普通透明')
        for w in self.plane_widgets:w.state(['disabled'] if surface else ['!disabled'])
        for w in self.surface_widgets:w.state(['!disabled'] if surface else ['disabled'])
        self.fields['lift'].state(['!disabled'] if glow else ['disabled'])
        self.update_selection_note();self.param_tabs.select(0);self.changed()

    def update_selection_note(self):
        selection=(self.project or {}).get('ae_selection')
        if not selection:
            self.selection_note.set('独立平面无需选择承载面，可直接拖动定位。' if self.placement.get()=='独立平面' else '尚未选择承载面')
            return
        count=sum(len(g['triangles']) for g in selection['groups'])
        self.selection_note.set(('已保留 %d 个三角面；当前独立平面不受此选区裁剪。' if self.placement.get()=='独立平面' else '已选择 %d 个三角面；双侧显示已开，会镜像到另一侧。' if self.mirror.get() else '已选择 %d 个三角面；当前仅显示所选侧，可勾选“左右双侧显示”。')%count)

    def clear_surface(self):
        if self.project:
            self.project.pop('ae_selection',None);self.project.pop('ae_surface_origin',None)
        if self.session:
            self.session.project.pop('ae_selection',None);self.session.project.pop('ae_surface_origin',None)
        self.update_selection_note();self.changed()

    def snap_preview(self):
        if self.placement.get()=='独立平面':self.placement.set('贴面发光' if self.blend.get()=='发光叠加' else '贴面播放')
        self.preview()

    def reset_deform(self):
        for key in ae.WARPS:self.values[key].set('0')
        self.note.set('四角已恢复矩形；平面位置和当前动画保留。')

    def new_plane(self):
        if getattr(self,'busy',False):self.note.set('正在处理，请稍候再新建平面。');return
        try:
            current=self.collect();clip=copy.deepcopy(self.clip or {'frame_size':[16,9]})
        except (ValueError,OSError) as error:self.note.set(str(error));return
        project=getattr(self,'project',None)
        pending_surface=current['placement']!='plane' and project and project.get('ae_selection') and self.clip
        snapshot=copy.deepcopy(project) if pending_surface else None
        def apply(values):
            if snapshot is not None:
                now=getattr(self,'project',None) or {}
                try:unchanged=self.collect()==current
                except (ValueError,OSError):unchanged=False
                for key in ('source_sha256','ae_selection','ae_surface_origin'):
                    unchanged=unchanged and now.get(key)==snapshot.get(key)
                if not unchanged or self.clip!=clip:
                    self.note.set('设置或选区已变化，请重新点击“新建流动平面”。');return
            self.placement.set('独立平面');self.mirror.set(values['mirror'])
            self.part.set(next(k for k,v in PARTS.items() if v==values['part']))
            self.plane.set(next(k for k,v in PLANES.items() if v==values['plane']))
            for key,var in self.values.items():var.set(str(values[key]))
            self.param_tabs.select(1);self.changed()
            self.note.set('已新建流动平面，保留当前方向和双侧设置。双侧平面需放在车体一侧。')
        if snapshot is not None:
            # Compute from the latest form and selected armor on a worker.
            # A session's last preview may still reflect older parameters.
            client=self.session.client if self.session else self.client.get() or None
            self.note.set('正在根据当前选区创建平面…')
            self.job(lambda:ae.new_plane_config(clip,current,ae.preview_data(clip,current,snapshot,client)),apply)
        else:
            try:apply(ae.new_plane_config(clip,current))
            except (ValueError,OSError) as error:self.note.set(str(error))

    def reset_fitting(self):
        for key in ('uv_scale','uv_scale_x','uv_scale_y','u_offset','v_offset','crop_left','crop_right','crop_top','crop_bottom'):
            self.values[key].set(str(ae.DEFAULTS[key]))
        self.note.set('缩放、偏移和裁剪已重置；当前吸附点与装甲选区保留。')

    def update_packaging(self):
        self.export_button.configure(text='生成涂装包')
        self.project_toggle.state(['!disabled'] if self.auto_bundle.get() else ['disabled'])

    def refresh_presets(self,selected=None):
        self.preset_records,issues=ae_presets.scan()
        names=[record['name'] for record in self.preset_records]
        self.preset_combo.configure(values=names)
        name=selected if selected in names else self.preset_name.get()
        self.preset_name.set(name if name in names else names[0] if names else '')
        self.preset_apply.state(['!disabled'] if names else ['disabled'])
        self.describe_preset()
        if issues:self.preset_note.set('有 %d 个预设无法读取；原文件已保留。可在管理中打开预设目录检查。'%len(issues))

    def selected_preset(self):
        return next((r for r in self.preset_records if r['name']==self.preset_name.get()),None)

    def describe_preset(self,*args):
        record=self.selected_preset()
        if not record:self.preset_note.set('还没有 AE 预设。导入 PNG 素材并调好参数后，点击“保存为预设”，或从管理中导入。');return
        self.preset_note.set(ae_presets.summary(record))

    def accept_preset(self,result):
        data,clip=result
        # No source, baseline, joint, selection or placement-mode changes here.
        values=ae_presets.apply_settings(self.collect(),data['config'])
        self.imported(clip)
        for key in ae_presets.SETTINGS:
            if key in self.values:self.values[key].set(str(values[key]))
        self.plane.set(next(k for k,v in PLANES.items() if v==values['plane']))
        self.blend.set(next(k for k,v in BLENDS.items() if v==values['blend']))
        self.note.set('已套用 AE 预设“'+data['name']+'”。当前涂装、位置和选区已保留；可继续微调并预览。')
        self.changed()

    def apply_preset(self):
        record=self.selected_preset()
        if not record:return
        # Validate the current form before starting, so applying is all-or-nothing.
        try:self.collect()
        except ValueError as error:return messagebox.showerror('参数有误',str(error),parent=self)
        path=record['path'];self.job(lambda:ae_presets.load(path,self.work/'presets'),self.accept_preset)

    def save_preset(self):
        if not self.clip:return messagebox.showinfo('先导入素材','请先导入 PNG 序列帧或图集，并调整播放和尺寸参数。保存预设不需要选择涂装。',parent=self)
        try:values=self.collect()
        except ValueError as error:return messagebox.showerror('参数有误',str(error),parent=self)
        name=simpledialog.askstring('保存 AE 预设','预设名称（最多 60 字）：',initialvalue=self.preset_name.get() or '我的 AE 特效',parent=self)
        if name is None:return
        target=ae_presets.library_file(name)
        if target.exists() and not messagebox.askyesno('更新 AE 预设','更新“'+name+'”？原预设会保存为 .bak 备份。',parent=self):return
        description=simpledialog.askstring('预设说明','简短说明（可留空）：',parent=self)
        if description is None:return
        clip=copy.deepcopy(self.clip)
        def work():
            data,payload=ae_presets.encode(name,description,clip,values)
            ae_presets.store(data,payload);return data['name']
        def saved(name):self.refresh_presets(name);self.note.set('AE 预设已保存，下次启动可直接套用：'+name)
        self.job(work,saved)

    def manage_presets(self):
        if self.busy:return
        dialog=tk.Toplevel(self);prepare_dialog(dialog,'AE 预设');dialog.geometry('780x580');dialog.minsize(700,500);dialog.transient(self);dialog.grab_set()
        box=ttk.Frame(dialog,padding=18,style='Backdrop.TFrame');box.pack(fill='both',expand=True)
        ttk.Label(box,text='AE 特效预设库',style='Section.TLabel').pack(anchor='w')
        ttk.Label(box,text='选择预设查看下方注释。可直接套用、导入或导出；素材、播放、调色和尺寸随预设保存，车辆位置与选区保留。',wraplength=700,style='Muted.TLabel').pack(anchor='w',pady=(6,12))
        footer=ttk.Frame(box);footer.pack(side='bottom',fill='x',pady=(12,0))
        # Reserve the notes/footer before the expanding list. Scrolling the
        # notes must never push import/export controls outside the dialog.
        notes=ttk.Frame(box);notes.pack(side='bottom',fill='x',pady=(10,0))
        description=tk.Text(notes,height=6,wrap='word',state='disabled',bg='#ffffff',fg='#526179',relief='flat',borderwidth=0,padx=8,pady=6,font=('Microsoft YaHei UI',10))
        register_widget(description,'field')
        note_scroll=ttk.Scrollbar(notes,orient='vertical',command=description.yview);description.configure(yscrollcommand=note_scroll.set)
        note_scroll.pack(side='right',fill='y');description.pack(side='left',fill='x',expand=True)
        main=ttk.Frame(box);main.pack(fill='both',expand=True)
        preview=tk.Canvas(main,width=280,height=190,bg='#141923',highlightthickness=0)
        preview.pack(side='right',padx=(12,0),anchor='n')
        listing=tk.Listbox(main,bg='white',fg='#1d1d1f',selectbackground='#e5f0ff',selectforeground='#1d1d1f',highlightthickness=1,highlightbackground='#dce3ec',exportselection=False)
        style_listbox(listing)
        scroll=ttk.Scrollbar(main,command=listing.yview);listing.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');listing.pack(side='left',fill='both',expand=True)
        def show_description(text):
            description.configure(state='normal');description.delete('1.0','end');description.insert('1.0',text);description.configure(state='disabled');description.yview_moveto(0)
        def chosen():
            indices=listing.curselection()
            return self.preset_records[indices[0]] if indices else None
        def describe(*args):
            record=chosen();preview.delete('all');preview.image=None
            show_description(ae_presets.description_text(record))
            if record:
                try:
                    from PIL import ImageTk
                    preview.image=ImageTk.PhotoImage(ae_presets.poster(record['path']),master=dialog)
                    preview.create_image(140,95,image=preview.image)
                except (ValueError,OSError) as error:show_description(ae_presets.description_text(record)+'\n\n缩略图未能显示：'+str(error))
        def refresh(selected=None):
            self.refresh_presets(selected);listing.delete(0,'end')
            for record in self.preset_records:listing.insert('end',record['name'])
            if self.preset_records:
                index=next((i for i,r in enumerate(self.preset_records) if r['name']==self.preset_name.get()),0)
                listing.selection_set(index);listing.see(index)
            describe()
        def apply():
            record=chosen()
            if record:self.preset_name.set(record['name']);dialog.destroy();self.apply_preset()
        def import_file():
            path=filedialog.askopenfilename(parent=dialog,title='导入 AE 预设',filetypes=[('AE 特效预设','*.aepreset')])
            if not path:return
            try:
                # Verify all bytes before any local preset is replaced.
                data,atlas=ae_presets.read(path);target=ae_presets.library_file(data['name'])
                if target.exists() and not messagebox.askyesno('同名预设','更新“'+data['name']+'”？原文件保留 .bak 备份。',parent=dialog):return
                ae_presets.store(data,Path(path).read_bytes());refresh(data['name']);self.note.set('AE 预设已导入：'+data['name'])
            except (ValueError,OSError) as error:messagebox.showerror('无法导入',str(error),parent=dialog)
        def export_file():
            record=chosen()
            if not record:return
            path=filedialog.asksaveasfilename(parent=dialog,title='导出 AE 预设',initialfile=ae.engine.title_name(record['name'])+ae_presets.SUFFIX,defaultextension=ae_presets.SUFFIX,filetypes=[('AE 特效预设','*.aepreset')])
            if not path:return
            try:
                ae_presets.read(record['path']);ae_presets.atomic_write(Path(path),record['path'].read_bytes())
                self.note.set('AE 预设已导出：'+path)
            except (ValueError,OSError) as error:messagebox.showerror('无法导出',str(error),parent=dialog)
        def remove():
            record=chosen()
            if not record or not messagebox.askyesno('删除 AE 预设','删除“'+record['name']+'”？原文件会保留为 .bak 备份。',parent=dialog):return
            try:
                path=record['path'];ae_presets.atomic_write(path.with_suffix(ae_presets.SUFFIX+'.bak'),path.read_bytes());path.unlink();refresh()
            except OSError as error:messagebox.showerror('无法删除',str(error),parent=dialog)
        def open_folder():
            ae_presets.LIBRARY_PATH.mkdir(parents=True,exist_ok=True);os.startfile(ae_presets.LIBRARY_PATH)
        listing.bind('<<ListboxSelect>>',describe);listing.bind('<Double-Button-1>',lambda event:apply())
        _preset_action_buttons(footer,[('套用',apply),('导入…',import_file),('导出…',export_file),('删除',remove),('预设目录',open_folder),('关闭',dialog.destroy)])
        refresh();self.attach_explanations(dialog)

    def attach_explanations(self,parent):
        """Attach the shared, non-focusing help popup to fields and actions.

        Numeric fields use parameter keys, so changing a caption cannot silently
        remove its units/help. Combobox choices use the same help as the field.
        """
        variables={str(value):key for key,value in self.values.items()}
        for name,key in [('source','source'),('client','client'),('baseline','baseline'),('part','part'),('plane','plane'),('placement','placement'),('blend','blend'),('mirror','mirror'),('preset_name','preset'),('premult','premult'),('columns','columns'),('rows','rows'),('count','count'),('auto_bundle','auto_bundle'),('include_project','include_project'),('output_folder','output_folder'),('title_value','title_value')]:variables[str(getattr(self,name))]=key
        def walk(widget):
            for child in widget.winfo_children():
                keys=child.keys();variable=child.cget('textvariable') if 'textvariable' in keys else child.cget('variable') if 'variable' in keys else ''
                key=variables.get(str(variable))
                if key:
                    if isinstance(child,ttk.Combobox):self.hover_help.attach_combobox(child,lambda event,k=key:ae_help.topic(k),lambda value,k=key:ae_help.option(k,value))
                    else:self.hover_help.attach(child,lambda event,k=key:ae_help.topic(k))
                elif 'text' in keys and str(child.cget('text')) in ae_help.TEXT:
                    key=str(child.cget('text'));self.hover_help.attach(child,lambda event,k=key:ae_help.topic(k))
                walk(child)
        walk(parent)

    def choose_output_folder(self):
        folder=filedialog.askdirectory(parent=self,title='选择成品保存目录')
        if folder:self.output_folder.set(folder)

    def open_results(self):
        path=Path(self.last_output).parent if self.last_output else Path(self.output_folder.get())
        path.mkdir(parents=True,exist_ok=True);os.startfile(path)

    def button(self,parent,text,command):
        button=ttk.Button(parent,text=text,command=command);self.buttons.append(button);return button

    def job(self,fn,done):
        if self.busy:return
        self.hover_help.hide()
        self.busy=True;start_progress(self.progress)
        self._busy_controls=lock_controls(self)
        def run():
            try:self.events.put(('done',done,fn()))
            except Exception as e:self.events.put(('error',None,str(e)))
        threading.Thread(target=run,daemon=True).start()

    def collect(self):
        return ae.config(dict({k:v.get() for k,v in self.values.items()},part=PARTS[self.part.get()],plane=PLANES[self.plane.get()],blend=BLENDS[self.blend.get()],mirror=self.mirror.get(),placement=PLACEMENTS[self.placement.get()]))

    def require(self):
        if not self.clip:raise ValueError('请先导入 PNG 序列帧或图集。')
        client=str(ae.engine.resolve_client_root(self.client.get()))
        if not self.source.get():raise ValueError('请先选择涂装包。')
        return client,self.collect(),self.source.get(),self.baseline.get()

    def get_project(self,source,baseline):
        if self.project is None or self.loaded_source!=str(Path(source).resolve()):
            self.project=ae.source_project(source,self.work/('source_'+datetime.now().strftime('%H%M%S%f')))
            self.loaded_source=str(Path(source).resolve())
        project=copy.deepcopy(self.project);project['baseline_user_confirmed']=baseline;return project

    def check_client(self):
        try:
            root=ae.engine.resolve_client_root(self.client.get());tree=ae.ET.parse(root/'version.xml');self.client_note.set((tree.findtext('meta/realm') or '')+' · '+(tree.findtext('version') or '').strip())
        except Exception as e:self.client_note.set(str(e))

    def choose_source(self):
        path=filedialog.askopenfilename(parent=self,title='选择单车型涂装包',filetypes=[('WOT 涂装','*.wotmod *.zip')])
        if path:
            self.source.set(path);self.project=None;self.loaded_source=None;self.selection_note.set('尚未选择承载面');self.baseline.set(False)
            if self.session:self.session.close();self.session=None

    def choose_client(self):
        path=filedialog.askdirectory(parent=self,title='选择实际运行的游戏目录（含 paths.xml）')
        if path:
            self.client.set(path);self.baseline.set(False);self.check_client()
            if self.session:self.session.close();self.session=None

    def imported(self,clip):
        self.clip=clip;w,h=clip['frame_size'];self.clip_note.set('%d 帧 · 原始 %d×%d · 图集 %d×%d · 已保留透明通道'%(clip['frames'],w,h,*clip['size']));self.note.set('素材已导入。可打开三维预览，或调整宽度、位置和帧率。');self.changed()

    def choose_frames(self):
        paths=filedialog.askopenfilenames(parent=self,title='选择同一组 PNG 序列帧（按文件名数字排序）',filetypes=[('透明 PNG','*.png')])
        if paths:
            premult=self.premult.get();dest=self.work/('atlas_'+datetime.now().strftime('%H%M%S%f')+'.png');self.job(lambda:ae.import_sequence(paths,dest,premult),self.imported)

    def choose_folder(self):
        path=filedialog.askdirectory(parent=self,title='选择只包含这一组序列帧的文件夹')
        if path:
            paths=list(Path(path).glob('*.png'));premult=self.premult.get();dest=self.work/('atlas_'+datetime.now().strftime('%H%M%S%f')+'.png');self.job(lambda:ae.import_sequence(paths,dest,premult),self.imported)

    def choose_sheet(self):
        try:cols,rows,count=map(int,(self.columns.get(),self.rows.get(),self.count.get()))
        except ValueError:return messagebox.showerror('图集设置','行、列和有效帧数请填写整数。',parent=self)
        path=filedialog.askopenfilename(parent=self,title='选择规则排列的透明 PNG 图集',filetypes=[('透明 PNG','*.png')])
        if path:
            premult=self.premult.get();dest=self.work/('atlas_'+datetime.now().strftime('%H%M%S%f')+'.png');self.job(lambda:ae.import_sheet(path,cols,rows,count,dest,premult),self.imported)

    def preview(self):
        try:client,c,source,baseline=self.require()
        except Exception as e:return messagebox.showerror('无法预览',str(e),parent=self)
        clip=copy.deepcopy(self.clip)
        def create():return preview3d.Session(self.get_project(source,baseline),client,effect=(clip,c))
        def opened(session):
            if self.session:self.session.close()
            self.session=session;self.note.set('三维预览已打开；调整参数会实时同步。点击“点击模型放置”可选择承载表面。')
        self.job(create,opened)

    def changed(self,*args):
        self.update_selection_note()
        value=self.values['tint_color'].get()
        if ae.re.fullmatch(r'#[0-9a-fA-F]{6}',value):self.color_swatch.configure(bg=value)
        if self.pending:self.after_cancel(self.pending)
        self.pending=self.after(300,self.update_live)

    def set_effect_color(self,color):
        self.values['tint_color'].set(color)
        try:strength=float(self.values['tint_strength'].get() or '0')
        except ValueError:strength=0
        if not 0<strength<=100:self.values['tint_strength'].set('100')

    def choose_effect_color(self):
        current=self.values['tint_color'].get()
        if not ae.re.fullmatch(r'#[0-9a-fA-F]{6}',current):current='#FFFFFF'
        _,color=colorchooser.askcolor(color=current,parent=self,title='选择 AE 特效颜色')
        if color:self.set_effect_color(color)

    def update_live(self):
        self.pending=None
        if self.session and self.clip:
            if self.live_worker:self.live_again=True;return
            try:values=self.collect()
            except (ValueError,OSError) as error:self.note.set(str(error));return
            session=self.session;clip=copy.deepcopy(self.clip);self.live_worker=True
            def run():
                try:
                    if not session.closed:session.update_effect(clip,values)
                    self.events.put(('live_done',None,None))
                except Exception as error:self.events.put(('live_done',None,str(error)))
            threading.Thread(target=run,daemon=True).start()

    def save(self):
        try:client,c,source,baseline=self.require()
        except Exception as e:return messagebox.showerror('无法保存',str(e),parent=self)
        path=filedialog.asksaveasfilename(parent=self,title='保存可移走后重开的 AE 工程',defaultextension='.aefx',filetypes=[('AE 特效工程','*.aefx')])
        if path:
            clip=copy.deepcopy(self.clip)
            self.job(lambda:ae.save_project(path,self.get_project(source,baseline),clip,c),lambda _:self.note.set('工程已保存：'+path))

    def load(self):
        path=filedialog.askopenfilename(parent=self,title='打开 AE 特效工程',filetypes=[('AE 特效工程','*.aefx')])
        if not path:return
        def loaded(result):
            if self.session:self.session.close();self.session=None
            project,clip,c=result;self.project=project;self.loaded_source=str(Path(project['source']).resolve());self.source.set(project['source']);self.baseline.set(project.get('baseline_user_confirmed',False));self.imported(clip)
            self.placement.set(next(k for k,v in PLACEMENTS.items() if v==c['placement']))
            self.update_selection_note()
            for k,v in self.values.items():v.set(str(c[k]))
            for var,mapping,key in [(self.part,PARTS,'part'),(self.plane,PLANES,'plane'),(self.blend,BLENDS,'blend')]:var.set(next(n for n,v in mapping.items() if v==c[key]))
            self.mirror.set(c['mirror']);self.note.set('工程已恢复，可直接预览或继续调整。')
        folder=self.work/('reopened_'+datetime.now().strftime('%H%M%S%f'));self.job(lambda:ae.load_project(path,folder),loaded)

    def export(self):
        try:client,c,source,baseline=self.require()
        except Exception as e:return messagebox.showerror('无法生成',str(e),parent=self)
        try:ae.validate_bilateral_placement(c)
        except ValueError as e:return messagebox.showerror('请调整双侧位置',str(e),parent=self)
        if not baseline:return messagebox.showerror('请先核对原版','确认原涂装在所选客户端正常后，勾选原版确认。',parent=self)
        title=self.title_value.get();clip=copy.deepcopy(self.clip);folder=Path(self.output_folder.get())/('AE_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        bundle=self.auto_bundle.get();include_project=self.include_project.get()
        def generate():
            project=self.get_project(source,baseline)
            path,report=ae.build(project,clip,c,client,folder,title)
            delivery=ae.bundle_delivery(path,report,project,clip,c,include_project) if bundle else None
            return path,report,delivery
        def built(result):
            path,report,delivery=result;shown=delivery['path'] if delivery else str(path);self.last_output=shown
            self.note.set('已生成并校验：'+shown);messagebox.showinfo('AE 特效包已生成',shown+'\n\n安装包 SHA256：'+report['artifact']['sha256']+'\n\n未自动安装，游戏整车与实际效果待实测。',parent=self)
        self.job(generate,built)

    def poll(self):
        """A failed UI callback must not stop polling or leave all controls locked."""
        try:self._poll_once()
        except Exception as error:
            self.busy=False;stop_progress(self.progress);unlock_controls(self._busy_controls);self._busy_controls=[]
            self.note.set('界面更新未完成：'+str(error));messagebox.showerror('界面更新未完成',str(error),parent=self)
        finally:
            if not self.closing:self.poll_id=self.after(150,self.poll)

    def _poll_once(self):
        try:
            while True:
                kind,done,value=self.events.get_nowait()
                if kind=='live_done':
                    self.live_worker=False
                    if value:self.note.set(value)
                    else:self.note.set('预览已同步。')
                    if self.live_again:self.live_again=False;self.changed()
                    continue
                self.busy=False;stop_progress(self.progress)
                unlock_controls(self._busy_controls);self._busy_controls=[]
                if kind=='error':self.note.set(value);messagebox.showerror('操作未完成',value,parent=self)
                elif done:done(value)
        except queue.Empty:pass
        if self.session:
            try:
                while True:
                    event=self.session.events.get_nowait()
                    if event['type']=='bodyselect':
                        selection=event['selection'];self.project['ae_selection']=copy.deepcopy(selection);self.session.project['ae_selection']=copy.deepcopy(selection)
                        # Clicked points are in the mesh's bind space, not the
                        # currently posed camera/world coordinates. Export checks
                        # containment against the original selected triangles.
                        if event.get('snap'):
                            origin=dict(source_sha256=self.project['source_sha256'],point=event['point'])
                            for project in (self.project,self.session.project):project['ae_surface_origin']=copy.deepcopy(origin)
                            self.plane.set('自动贴合')
                            for key in ('u_offset','v_offset'):self.values[key].set('0')
                        else:
                            self.project.pop('ae_surface_origin',None);self.session.project.pop('ae_surface_origin',None)
                        self.update_selection_note()
                        # Ordinary selection only edits the carrying region.
                        # Changing placement fires mode defaults and would erase
                        # the user's explicit blend and mapping direction.
                        if event.get('snap') and self.placement.get()=='独立平面':self.placement.set('贴面发光' if self.blend.get()=='发光叠加' else '贴面播放')
                        self.changed()
                    elif event['type']=='effectplane':self.new_plane()
                    elif event['type']=='effectparams':
                        for key,value in event['values'].items():
                            if key=='mirror':self.mirror.set(value)
                            else:self.values[key].set(str(value))
                        self.changed()
                    elif event['type']=='effectplace':
                        self.part.set(next(k for k,v in PARTS.items() if v==event['part']))
                        for k,value in zip(('x','y','z'),event['position']):self.values[k].set('%.4f'%value)
                    elif event['type']=='closed':self.session.close();self.session=None;break
            except queue.Empty:pass
            if self.session and self.session.viewer and self.session.viewer.poll() is not None:self.session.close();self.session=None

    def close(self):
        if self.busy:self.note.set('正在完成当前处理，请完成后关闭窗口。');return
        if self.pending:self.after_cancel(self.pending)
        self.hover_help.hide()
        self.closing=True
        self.after_cancel(self.poll_id)
        if self.session:self.session.close()
        self.destroy()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',default='');parser.add_argument('--client',default='');args=parser.parse_args();AEImporter(args.source,args.client).mainloop()
