"""Chinese desktop light extractor and recipe maker: python -m wotcamo.light_gui."""
import copy
import json
import os
import queue
import tempfile
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
from pathlib import Path
import numpy as np
from .common import ROOT
from . import light_effects as engine
from . import light_support as support
from . import light_presets as presets
from . import light_select
from . import light_help
from . import light_preview
from . import preview3d_preferences, autosave
from .light_tooltips import HoverHelp
from . import __version__, APP_NAME
from .ui_theme import start_progress, stop_progress, prepare_dialog, style_listbox, register_widget, lock_controls, unlock_controls

APP_VERSION = __version__

class LightMaker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.app_version=APP_VERSION
        self.title(APP_NAME+' · 灯效制作')
        width=min(1320,max(980,self.winfo_screenwidth()-60))
        height=min(960,max(620,self.winfo_screenheight()-80))
        self.geometry('%dx%d'%(width,height)); self.minsize(980, 620)
        self.option_add('*Font', ('Microsoft YaHei UI', 10))
        self.project = None; self.last_output = None; self.busy = False
        self._busy_controls=[]
        self.auto_save=tk.BooleanVar(value=autosave.enabled('lights'))
        self._autosave_running=False; self._autosave_after=None
        self.events = queue.Queue(); self.records = {}; self.active = None
        self.picked = set(); self._syncing = False
        self.pick_text = tk.StringVar(value='套选：0 块灯面')
        self._drag_origin = None; self._drag_rect = None; self._preview_view = None
        self._preview_zoom=1.0;self._preview_pan=np.zeros((3,2));self._pan_origin=None
        self._preview_keys=None
        self.zoom_text=tk.StringVar(value='100%')
        self.source = tk.StringVar()
        # The user's actual game can be on another computer or in another region.
        self.client = tk.StringVar(value='')
        self.baseline = tk.BooleanVar(value=False)
        self.auto_install = tk.BooleanVar(value=False)
        self.auto_bundle = tk.BooleanVar(value=True)
        self.output_folder = tk.StringVar(value=str(ROOT/'result/灯效制作器'))
        self.embed_recoverable = tk.BooleanVar(value=True)
        self.log_since_mark = tk.BooleanVar(value=True)
        self.last_install = None
        self.status = tk.StringVar(value='选择原始涂装并提取灯面；可选生成后安装，或提取报错日志。')
        self.colors = tk.StringVar(value='#0838FF, #FF1A75, #FFBF0A')
        self.step = tk.StringVar(value='2'); self.breath = tk.StringVar(value='2')
        self.peak = tk.StringVar(value='2'); self.low = tk.StringVar(value='0.08')
        self.delay = tk.StringVar(value='0.65'); self.direction = tk.StringVar(value='向车头')
        self.effect_mode=tk.StringVar(value='流水呼吸');self.duty=tk.StringVar(value='0.3')
        self.color_curve=tk.StringVar(value='柔和')
        self.dimming=tk.BooleanVar(value=True)
        self._dimming_preference=True
        self._last_effect_mode=self.effect_mode.get()
        try:self.preset_library=presets.load()
        except (ValueError,OSError):self.preset_library=presets.defaults()
        self.preset_library=presets.with_new_presets(self.preset_library)
        self.title_value = tk.StringVar(value='自定义灯效')
        self.widgets = []
        self.edit_scope = tk.StringVar(value='全局配方')
        self.editor_hint = tk.StringVar(value='全局配方 · 用于未设置独立配方的模型，保存或生成时生效。')
        self._editor_scope = '全局配方'
        self._local_form_baseline = None
        self._global_form_baseline = None
        self.engine_modes = engine.light_recipe.MODES
        self.engine_directions = engine.light_recipe.DIRECTIONS
        self.hover_help=HoverHelp(self)
        self._closing=False
        self._drain_after=None
        self.preview_mode=tk.StringVar(value='位置示意')
        self.live_note=tk.StringVar(value='实时灯效为离线模拟；游戏材质、泛光及遮挡需实测。')
        self.live_play_text=tk.StringVar(value='暂停')
        self.preview_caption=tk.StringVar(value='Shift 加选 · Ctrl 减选 · Alt 整模型')
        self._live_after=None;self._live_edit_after=None
        self._live_results=queue.Queue();self._live_worker=False
        self._live_key=None;self._live_plan=[];self._live_tags=[]
        self._live_last_colors={}
        self._live_pending=None;self._live_elapsed=0.;self._live_start=time.perf_counter()
        self._live_paused=False;self._live_error=False
        self.preview3d=None;self._three_after=None;self._three_update_after=None
        self.performance=tk.StringVar(value=preview3d_preferences.load())
        self.performance_profiles=tuple(preview3d_preferences.PROFILES)
        from .light_theme import build_interface
        build_interface(self)
        for var in (self.colors,self.step,self.breath,self.peak,self.low,self.delay,
                    self.direction,self.effect_mode,self.duty,self.edit_scope,self.color_curve,self.dimming):
            var.trace_add('write',self.preview_form_changed)
        self.effect_mode.trace_add('write',self.effect_mode_changed)
        self.direction.trace_add('write',self.update_param_states)
        self.low.trace_add('write',self.update_param_states)
        self.dimming.trace_add('write',self.update_param_states)
        self.update_param_states()
        self.bind('<Control-s>',lambda event:self.save_project())
        self.performance.trace_add('write',self.performance_changed)
        self._drain_after=self.after(100,self.drain)
        self._autosave_after=self.after(autosave.INTERVAL_MS,self.autosave_tick)

    def destroy(self):
        self._closing=True
        for name in ('_live_after','_live_edit_after','_three_after','_three_update_after','_autosave_after'):
            if getattr(self,name,None) is not None:
                try:self.after_cancel(getattr(self,name))
                except tk.TclError:pass
                setattr(self,name,None)
        if hasattr(self,'hover_help'):self.hover_help.hide()
        if self.preview3d:self.preview3d.close();self.preview3d=None
        if getattr(self,'_drain_after',None) is not None:
            try:self.after_cancel(self._drain_after)
            except tk.TclError:pass
            self._drain_after=None
        super().destroy()

    def button(self,parent,text,callback):
        b=ttk.Button(parent,text=text,command=callback);self.widgets.append(b)
        self.hint(b,text)
        return b

    def hint(self,widget,name):
        self.hover_help.attach(widget,lambda event:light_help.topic(name))
        return widget

    def tree_help(self,event):
        row=self.tree.identify_row(event.y)
        light=self.records.get(row)
        if not light:return light_help.topic('灯面资料库')
        title=light.get('material','灯面')
        state='已勾选，将参与生成' if light.get('selected') else '尚未勾选，不参与生成'
        if light.get('recovered_model') and not light.get('selected'):
            state='未勾选：重新生成时保留成品包中的原效果'
        supported='可自动制作' if light['supported'] else '需适配：'+light.get('reason','未提供原因')
        recipe='使用独立配方' if engine.override_recipe(light) else '跟随全局配方'
        return light_help.Help(title,'%s\n%s；%s。\n挂点：%s；三角面：%s。\n\n单击或 Ctrl/Shift 多选，双击切换生成勾选。套选后可按整个独立模型一起设置参数。'%
                               (state,supported,recipe,light.get('anchor','—'),light.get('triangles',0)))

    def job(self,func,done):
        if self.busy:return
        self.hover_help.hide()
        self.busy=True;start_progress(self.progress)
        self._busy_controls=lock_controls(self)
        def run():
            try:self.events.put(('done',(done,func())))
            except Exception as error:
                self.write_error(traceback.format_exc())
                self.events.put(('error',str(error)))
        threading.Thread(target=run,daemon=True).start()

    def drain(self):
        self._drain_after=None
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='log':self.status.set(data);continue
                if kind=='autosave':
                    self._autosave_running=False
                    self.status.set(data)
                    continue
                self.busy=False;stop_progress(self.progress)
                unlock_controls(self._busy_controls);self._busy_controls=[]
                if kind=='error':self.status.set(data);messagebox.showerror('未完成',data)
                else:
                    callback,result=data;callback(result)
        except queue.Empty:pass
        except Exception:
            self.write_error(traceback.format_exc())
            self.busy=False;stop_progress(self.progress)
            unlock_controls(self._busy_controls);self._busy_controls=[]
            self.status.set('操作未完成，详细错误已记录在程序缓存中。')
            messagebox.showerror('操作未完成','操作出错，详细记录已保存到程序缓存的 last_error.log。')
        finally:
            if not self._closing:
                self.update_param_states()
                self._drain_after=self.after(100,self.drain)

    def write_error(self,detail):
        try:
            folder=ROOT/'.cache';folder.mkdir(exist_ok=True)
            with (folder/'last_error.log').open('a',encoding='utf-8') as f:f.write(detail+'\n')
        except OSError:pass

    def report_callback_exception(self,exc,value,tb):
        self.write_error(''.join(traceback.format_exception(exc,value,tb)))
        self.status.set('界面操作未完成；详细错误已记录。')
        messagebox.showerror('操作未完成','界面操作出错，详细记录已保存到程序缓存的 last_error.log。')

    def effect_mode_changed(self,*_):
        if self._last_effect_mode not in engine.light_recipe.COLOR_ONLY_MODES:
            self._dimming_preference=self.dimming.get()
        mode=self.effect_mode.get();self._last_effect_mode=mode
        self.dimming.set(mode not in engine.light_recipe.COLOR_ONLY_MODES and self._dimming_preference)
        self.update_param_states()

    def update_param_states(self,*_):
        """Disable controls ignored by the selected mode without erasing values."""
        if not hasattr(self,'parameter_entries'):return
        mode=self.effect_mode.get()
        dimming=self.dimming.get() and mode not in engine.light_recipe.COLOR_ONLY_MODES
        if hasattr(self,'dimming_check'):
            self.dimming_check.state(['disabled'] if self.busy or mode in engine.light_recipe.COLOR_ONLY_MODES else ['!disabled'])
        for name,widget in self.parameter_entries.items():
            disabled=self.busy or (name in ('呼吸周期','暗相系数') and not dimming) or (name=='亮灯比例' and (mode!='跑马灯' or not dimming)) or (name=='每米延迟' and self.direction.get()=='同步')
            widget.state(['disabled'] if disabled else ['!disabled'])
        if hasattr(self,'scan_issue_button'):
            disabled=self.busy or not self.project or not self.project.get('scan_issues')
            self.scan_issue_button.state(['disabled'] if disabled else ['!disabled'])
        self.update_actions()
        if hasattr(self,'editor_hint'):self.update_editor_hint()

    def update_actions(self):
        """Keep actions aligned with the current project, picks and build state."""
        if not hasattr(self,'apply_button'):return
        picked=bool(self.project and any(x['id'] in self.picked and x['supported'] for x in self.project['lights']))
        selected=bool(self.project and any(x.get('selected') and x.get('supported') for x in self.project['lights']))
        for name,enabled in (('build_button',selected),('save_button',bool(self.project and self.project['lights'])),
                             ('read_recipe_button',picked),('apply_button',picked),('restore_recipe_button',picked),
                             ('clear_all_button',bool(self.project))):
            getattr(self,name).state(['!disabled'] if enabled and not self.busy else ['disabled'])

    def log(self,message):self.events.put(('log',message))

    def change_autosave(self):
        try: autosave.set_enabled('lights',self.auto_save.get())
        except OSError as error: self.status.set('自动保存开关未能记住：'+str(error))

    def autosave_state(self):
        names=('colors','step','breath','peak','low','delay','direction','effect_mode','duty','color_curve','dimming','title_value')
        return dict(form={name:getattr(self,name).get() for name in names},scope=self.edit_scope.get(),
                    picked=sorted(self.picked),active=self.active['id'] if self.active else None,
                    global_baseline=copy.deepcopy(self._global_form_baseline),
                    local_baseline=copy.deepcopy(self._local_form_baseline),
                    client=self.client.get(),baseline=self.baseline.get(),embed=self.embed_recoverable.get())

    def autosave_tick(self):
        self._autosave_after=None
        delay=autosave.INTERVAL_MS
        try:
            if self.auto_save.get() and self.project:
                if self.busy or self._autosave_running:
                    delay=10000
                else:
                    snapshot=self.project_snapshot(); state=self.autosave_state()
                    snapshot['baseline_user_confirmed']=self.baseline.get()
                    snapshot['embed_recoverable']=self.embed_recoverable.get()
                    path=autosave.new_path('灯效工程','.wotlights',snapshot['source_sha256'])
                    self._autosave_running=True
                    def run():
                        try:
                            engine.save_project(snapshot,path,autosave_ui=state)
                            autosave.prune(path)
                            message='灯效工程已自动保存：'+str(path)
                        except Exception as e:
                            message='灯效工程自动保存失败：'+str(e)
                        self.events.put(('autosave',message))
                    threading.Thread(target=run,daemon=True).start()
        except Exception as error: self.status.set('灯效工程自动保存失败：'+str(error))
        finally:
            if not self._closing:self._autosave_after=self.after(delay,self.autosave_tick)

    def restore_autosave(self):
        if self.busy:return
        folder=autosave.FOLDER/'灯效工程'
        path=filedialog.askopenfilename(title='选择自动保存的灯效工程',initialdir=str(folder if folder.exists() else ROOT),filetypes=[('灯光工程','*.wotlights')])
        if not path:return
        self.source.set(path);work=self.work_dir()
        self.job(lambda:engine.load_project(path,work,self.log),self.set_project)

    def restore_autosave_state(self,state):
        if not isinstance(state,dict) or not isinstance(state.get('form'),dict):return
        names=('colors','step','breath','peak','low','delay','direction','effect_mode','duty','color_curve','dimming','title_value')
        form=state['form']
        for name in names:
            value=form.get(name)
            if (name=='dimming' and type(value) is bool) or (name!='dimming' and isinstance(value,str)):
                getattr(self,name).set(value)
        scope=state.get('scope')
        if scope in ('全局配方','套选模型','套选灯面'):
            self.edit_scope.set(scope);self._editor_scope=scope
        self._global_form_baseline=state.get('global_baseline')
        self._local_form_baseline=state.get('local_baseline')
        picked=state.get('picked',[])
        self.picked={x for x in picked if isinstance(x,str) and x in self.records} if isinstance(picked,list) else set()
        self.active=self.records.get(state.get('active'))
        if isinstance(state.get('client'),str):self.client.set(state['client'])
        if type(state.get('baseline')) is bool:self.baseline.set(state['baseline'])
        if type(state.get('embed')) is bool:self.embed_recoverable.set(state['embed'])
        self.sync_pick();self.update_editor_hint()
        self.status.set('已恢复自动保存的工程和表单草稿；局部草稿仍需应用。')

    def project_snapshot(self):
        """Freeze editable metadata before a worker starts reading the project."""
        # The editor treats geometry as immutable; copy mutable metadata and share
        # read-only views to avoid doubling large mesh buffers in memory.
        memo={}
        for light in self.project['lights']:
            for value in light.values():
                if isinstance(value,np.ndarray):
                    view=value.view();view.flags.writeable=False;memo[id(value)]=view
        return copy.deepcopy(self.project,memo)
    def work_dir(self):
        (ROOT/'.cache').mkdir(exist_ok=True)
        return Path(tempfile.mkdtemp(prefix='light_maker_',dir=ROOT/'.cache'))

    def choose_source(self):
        p=filedialog.askopenfilename(title='选择原始涂装或制作器成品包',filetypes=[('WOT 涂装','*.wotmod *.zip')])
        if not p:return
        self.source.set(p);work=self.work_dir()
        self.job(lambda:engine.scan(p,work,self.log,allow_body=True),self.set_project)

    def open_project(self):
        p=filedialog.askopenfilename(filetypes=[('灯光工程','*.wotlights')])
        if not p:return
        self.source.set(p);work=self.work_dir()
        self.job(lambda:engine.load_project(p,work,self.log),self.set_project)

    def choose_client(self):
        p=filedialog.askdirectory(title='选择游戏目录（包含 version.xml 和 paths.xml；误选子目录也会自动识别）')
        if not p:return
        try:root=engine.resolve_client_root(p)
        except ValueError as error:messagebox.showerror('游戏目录未识别',str(error));return
        self.client.set(str(root));self.baseline.set(False)
        self.status.set('已识别游戏目录：'+str(root))

    def set_project(self,project):
        if self.preview3d:self.preview3d.close();self.preview3d=None
        self._live_key=None;self._live_plan=[];self._live_pending=None
        self.project=project;self.records={x['id']:x for x in project['lights']}
        self._variant_aliases=engine.variant_aliases(project['lights'])
        self.embed_recoverable.set(project.get('embed_recoverable',True))
        if project.get('embedded_restore'):
            self.recovery_hint.configure(text='内嵌工程已恢复：原始输入、灯面分组、勾选和已应用配方已还原。完整程度以生成时工程为准；此前已丢失的数据不会补回。')
            self.recovery_hint.grid()
        elif project.get('recovery'):
            self.recovery_hint.configure(text='成品恢复：可修改颜色、亮度、节奏并另存工程。未勾选的恢复模型保留原效果；原灯面分组和中和前颜色不能完整找回。')
            self.recovery_hint.grid()
        else:self.recovery_hint.grid_remove()
        self._preview_zoom=1.0;self._preview_pan=np.zeros((3,2));self._pan_origin=None
        self._preview_keys=None
        self.zoom_text.set('100%')
        self.edit_scope.set('全局配方');self._editor_scope='全局配方'
        self._local_form_baseline=None
        self.update_editor_hint()
        self.active=None;self.picked=set()
        self.tree.delete(*self.tree.get_children());parents={}
        names={'chassis':'底盘 / 轮灯','hull':'车体','turret':'炮塔 / 装饰','gun':'炮管'}
        vehicles={}
        for light in project['lights']:
            if light['vehicle'] not in vehicles:
                vehicles[light['vehicle']]=self.tree.insert('', 'end',text=light['vehicle'],open=True)
            group=(light['vehicle'],light['part'],light['visual'])
            if group not in parents:
                label=names.get(light['part'],light['part'])
                if light.get('recovered_model'):label+='（成品恢复）'
                elif '/normal/lod0/' not in light['visual'].lower():label+='（其他 LOD / 外观）'
                parents[group]=self.tree.insert(vehicles[light['vehicle']],'end',text=label,open=light.get('recovered_model') or '/normal/lod0/' in light['visual'].lower())
            self.tree.insert(parents[group],'end',iid=light['id'],text=self.item_text(light),
                             values=('可制作' if light['supported'] else '需适配',light['anchor'],light['triangles']),tags=() if light['supported'] else ('unsupported',))
        self.fill_recipe(project['recipe'])
        self._global_form_baseline=copy.deepcopy(self.read_form())
        self.preset.set('工程中的配方')
        self.baseline.set(project.get('baseline_user_confirmed',False))
        self.status.set('提取完成。可在预览里拖框套选灯面或整个模型，再一起勾选或设置参数。' if project['lights'] else '该包没有现有灯面；可打开三维预览框选车体。')
        if project.get('recovery'):
            self.status.set('成品包已恢复为可编辑工程。可修改配方并保存工程；未勾选的恢复模型会保留原效果。')
        if project.get('embedded_restore'):
            self.status.set('已完整恢复内嵌工程，可继续编辑并保存；请重新核对实际游戏客户端。')
        issues=project.get('scan_issues',[])
        if issues:
            self.status.set(self.status.get()+' 发现 %d 项资源问题，可点“查看资源问题”。'%len(issues))
        self.scan_issue_button.state(['!disabled'] if issues else ['disabled'])
        self.sync_pick(preserve=False)
        self.restore_autosave_state(project.pop('_autosave_ui',None))

    def show_scan_issues(self):
        """Show scan evidence without treating it as a game compatibility result."""
        if not self.project:return
        issues=self.project.get('scan_issues',[])
        dialog=tk.Toplevel(self);prepare_dialog(dialog,'资源问题');dialog.geometry('720x440');dialog.transient(self)
        box=ttk.Frame(dialog,padding=12);box.pack(fill='both',expand=True)
        ttk.Label(box,text='以下资源未能完整读取；仅供定位，不自动判断游戏兼容性。').pack(anchor='w')
        ttk.Button(box,text='关闭',command=dialog.destroy).pack(side='bottom',anchor='e')
        body=ttk.Frame(box);body.pack(fill='both',expand=True,pady=8)
        scroll=ttk.Scrollbar(body,orient='vertical');scroll.pack(side='right',fill='y')
        text=tk.Text(body,wrap='word',yscrollcommand=scroll.set,bg='white',fg='#1d1d1f',font=('Microsoft YaHei UI',10),relief='flat',padx=10,pady=8);text.pack(side='left',fill='both',expand=True)
        register_widget(text,'field')
        scroll.configure(command=text.yview)
        for item in issues:
            text.insert('end','%s\n%s\n\n'%(item.get('visual',item.get('resource','未知资源')),item.get('issue','未提供原因')))
        text.configure(state='disabled')

    def item_text(self,light):
        mark='⚙ ' if engine.override_recipe(light) else ''
        label=mark+light['material']
        if light['component']:label+=' #%d'%light['component']
        return ('☑ ' if light.get('selected') else '☐ ')+label

    def fill_recipe(self,cfg):
        colors=[]
        for color in cfg['颜色']:
            rgb=color['RGB'];colors.append(rgb if isinstance(rgb,str) else '#'+''.join('%02X'%round(x*255) for x in rgb))
        self.colors.set(', '.join(colors))
        for var,key in [(self.step,'每色秒数'),(self.breath,'呼吸周期秒数'),(self.peak,'峰值倍率'),(self.low,'暗相系数'),(self.delay,'每米延迟秒数'),(self.direction,'流水方向')]:var.set(str(cfg[key]))
        self.effect_mode.set(cfg.get('效果模式','流水呼吸'));self.duty.set(str(cfg.get('亮灯比例',.3)))
        self.color_curve.set('匀速无缝' if cfg.get('换色曲线')=='匀速' else '柔和')
        self.dimming.set(cfg.get('效果模式','流水呼吸') not in engine.light_recipe.COLOR_ONLY_MODES and cfg.get('启用明暗变化',True))
        self._dimming_preference=self.dimming.get()

    def select_all(self,value):
        if self.busy or not self.project:return
        for light in self.project['lights']:
            light['selected']=bool(value and light['supported']);self.refresh_item(light)
        self.update_count();self.draw_preview()

    def refresh_item(self,light):
        self.tree.item(light['id'],text=self.item_text(light))

    def toggle_current(self):
        if self.busy or not self.tree.selection():return
        ids=set()
        for key in self.tree.selection():
            ids.update([key] if key in self.records else self.collect_lights(key))
        lights=[self.records[i] for i in ids if i in self.records and self.records[i]['supported']]
        if not lights:return
        value=not all(x.get('selected') for x in lights)
        for light in lights:light['selected']=value;self.refresh_item(light)
        self.update_count();self.draw_preview()

    def collect_lights(self,item):
        ids=[]
        for child in self.tree.get_children(item):
            if child in self.records:ids.append(child)
            else:ids.extend(self.collect_lights(child))
        return ids

    def update_count(self):
        if self.project:self.count_label.configure(text='已选 %d / 可制作 %d 块灯面'%(sum(x.get('selected',False) for x in self.project['lights']),sum(x['supported'] for x in self.project['lights'])))
        self.update_actions()

    def picked_lights(self):
        if not self.project:return []
        return [x for x in self.project['lights'] if x['id'] in self.picked]

    def with_variant_aliases(self,identifiers):
        """Include identical physical faces across supported appearance variants."""
        result=set(identifiers)
        for identifier in tuple(result):result.update(self._variant_aliases.get(identifier,()))
        return result

    def refresh_pick_text(self):
        if not self.project:
            self.pick_text.set('套选：0 块灯面');return
        independent=len({light_select.model_key(x) for x in self.project['lights'] if engine.override_recipe(x)})
        text='套选：%d 块灯面 / %d 个模型'%(len(self.picked),light_select.model_count(self.project['lights'],self.picked))
        if independent:text+='；已设独立配方 %d 个模型'%independent
        self.pick_text.set(text)
        self.update_editor_hint()
        self.update_actions()

    def update_editor_hint(self):
        if self.edit_scope.get()=='全局配方':
            self.editor_hint.set('全局配方 · 未设独立配方的模型使用此设置，保存或生成时生效。')
        elif self.edit_scope.get()=='套选灯面':
            count=len(self.picked)
            self.editor_hint.set('单灯面编辑 · 套选 %d 块灯面；修改后点“应用到套选灯面”。'%count)
        else:
            count=light_select.model_count(self.project['lights'],self.picked) if self.project else 0
            self.editor_hint.set('局部编辑 · 套选 %d 个模型；修改后点“应用到套选模型”，全局配方保持不变。'%count)
        if self.effect_mode.get() in engine.light_recipe.COLOR_ONLY_MODES or not self.dimming.get():
            self.editor_hint.set(self.editor_hint.get()+' 明暗变化已关闭，只换色。')
        else:
            try:flat=float(self.low.get())==1
            except ValueError:flat=False
            if flat:self.editor_hint.set(self.editor_hint.get()+' 暗相为 1 时关闭明暗倍率起伏；换色仍可能改变观感亮度。')
        if hasattr(self,'apply_button'):
            self.apply_button.configure(text='应用到套选灯面' if self.edit_scope.get()=='套选灯面' else '应用到套选模型')

    def change_edit_scope(self):
        """Switch editors without letting a local form become the global recipe."""
        target=self.edit_scope.get()
        if target==self._editor_scope:return
        try:
            current=self.read_form()
            if self._editor_scope=='全局配方':
                self.commit_global_form(current)
            elif self._local_form_baseline is not None and current!=self._local_form_baseline:
                raise ValueError('局部参数尚未应用，请先应用到套选，或放弃草稿，再切换编辑范围。')
        except ValueError as error:
            self.edit_scope.set(self._editor_scope)
            messagebox.showerror('参数未保存',str(error),parent=self)
            return
        self._editor_scope=target
        if target=='全局配方':
            if self.project:
                self.fill_recipe(self.project['recipe'])
                self._global_form_baseline=copy.deepcopy(self.read_form())
        else:
            # A separate local draft starts from the saved global recipe. Reading
            # existing model overrides is explicit, so picking faces cannot discard edits.
            if self.project:self.fill_recipe(self.project['recipe'])
            self._local_form_baseline=copy.deepcopy(self.read_form())
        self.update_editor_hint()

    def load_picked_recipe(self):
        if self.busy or not self.project:return
        lights=[x for x in self.picked_lights() if x['supported']]
        if not lights:self.status.set('先套选可制作灯面，再读取它们的配方。');return
        try:current=self.read_form()
        except ValueError as error:
            messagebox.showerror('参数有误',str(error),parent=self);return
        if self._editor_scope in ('套选模型','套选灯面') and self._local_form_baseline is not None:
            if current!=self._local_form_baseline:
                self.status.set('局部参数尚未应用，请先应用，再读取其它模型的配方。');return
        elif self._editor_scope=='全局配方':
            self.commit_global_form(current)
        # Compare after committing the global draft: global-following models may
        # now differ from models with a previously identical explicit override.
        recipes=[engine.override_recipe(x) or self.project['recipe'] for x in lights]
        signature=json.dumps(recipes[0],sort_keys=True,ensure_ascii=False)
        if any(json.dumps(x,sort_keys=True,ensure_ascii=False)!=signature for x in recipes[1:]):
            self.status.set('套选对象的配方不同，请只选一组相同配方再读取。');return
        scope='套选灯面' if self.edit_scope.get()=='套选灯面' else '套选模型'
        self.edit_scope.set(scope);self._editor_scope=scope
        self.fill_recipe(recipes[0])
        self._local_form_baseline=copy.deepcopy(self.read_form())
        self.update_editor_hint()
        self.status.set('已读取套选配方；修改后点“应用到套选”。')

    def commit_global_form(self,cfg):
        # Displaying a float palette as hex is lossy. Merely switching tabs must
        # not rewrite an unchanged recipe or strip its original colour names.
        if self.project and cfg!=self._global_form_baseline:
            self.project['recipe']=copy.deepcopy(cfg)
            self._global_form_baseline=copy.deepcopy(cfg)

    def discard_recipe_draft(self):
        if self.busy or not self.project:return
        if self.edit_scope.get() in ('套选模型','套选灯面') and self._local_form_baseline is not None:
            self.fill_recipe(self._local_form_baseline)
        else:
            self.fill_recipe(self.project['recipe'])
            self._global_form_baseline=copy.deepcopy(self.read_form())
        self.status.set('已放弃当前草稿的未应用修改。')

    def describe_active(self):
        if not self.project:return
        if self.active:
            a=self.active
            text='%s · 挂点 %s · %d 面 · %s'%(Path(a['visual']).name,a['anchor'],a['triangles'],'可自动制作' if a['supported'] else a['reason'])
            if engine.override_recipe(a):text+=' · 独立配方'
            self.detail.set(text);self.show_detail(True)
        elif self.picked:
            self.detail.set('套选 %d 块灯面 / %d 个模型；用下方按钮批量勾选或一起设置。'%(len(self.picked),light_select.model_count(self.project['lights'],self.picked)))
            self.show_detail(True)
        else:
            self.detail.set('');self.show_detail(False)

    def show_detail(self,visible):
        mapped=self.detail_label.winfo_ismapped()
        if visible and not mapped:self.detail_label.pack(fill='x',after=self.canvas)
        elif not visible and mapped:self.detail_label.pack_forget()

    def sync_pick(self,preserve=True):
        if not self.project:
            self.pick_text.set('套选：0 块灯面');return
        if not preserve:self.active=None
        elif self.active and self.active['id'] not in self.picked:self.active=None
        self._syncing=True
        try:
            keys=[key for key in self.picked if key in self.records]
            existing=self.tree.selection()
            if existing:self.tree.selection_remove(*existing)
            if keys:self.tree.selection_set(*keys)
            if self.active and self.active['id'] in self.records:self.tree.see(self.active['id'])
        finally:self._syncing=False
        self.describe_active();self.refresh_pick_text();self.update_count();self.draw_preview()

    def on_pick(self,event=None):
        if self._syncing or not self.project:return
        keys=[]
        for key in self.tree.selection():
            keys.extend([key] if key in self.records else self.collect_lights(key))
        self.picked=set(keys)
        self.active=self.records.get(keys[-1]) if keys else None
        self.describe_active();self.refresh_pick_text();self.draw_preview()

    def draft_targets(self,scope=None,supported_only=False):
        scope=scope or self.edit_scope.get()
        picked={x for x in self.picked if x in self.records and (not supported_only or self.records[x]["supported"])}
        local_keys={light_select.model_key(self.records[x]) for x in picked}
        return self.with_variant_aliases(x['id'] for x in self.project['lights'] if
            (scope=='套选模型' and light_select.model_key(x) in local_keys) or
            (scope=='套选灯面' and x['id'] in picked))

    def effective_recipes(self):
        if not self.project:raise ValueError('请先提取原始涂装或打开灯光工程。')
        draft=self.read_form();global_recipe=self.project['recipe']
        if self.edit_scope.get()=='全局配方' and draft!=self._global_form_baseline:
            global_recipe=draft
        targets=self.draft_targets();lights=[]
        for light in self.project['lights']:
            item=dict(light)
            if draft!=self._local_form_baseline and light['id'] in targets:item['配方']=draft
            lights.append(item)
        return global_recipe,lights

    def preview3d_state(self):
        global_recipe,lights=self.effective_recipes()
        return dict(recipe=copy.deepcopy(global_recipe),
                    lights=copy.deepcopy([dict(id=x['id'],selected=bool(x.get('selected')),recipe=x.get('配方')) for x in lights]),
                    picked=sorted(self.picked),performance=preview3d_preferences.PROFILES.get(self.performance.get(),'balanced'))

    def performance_changed(self,*args):
        if self._closing:return
        try:preview3d_preferences.save(self.performance.get())
        except (OSError,ValueError) as error:self.status.set('性能档本次已应用，但未保存偏好：'+str(error))
        self.schedule_preview3d()

    def open_preview3d(self):
        if self.busy:return
        if self.preview3d and not self.preview3d.closed and self.preview3d.viewer.poll() is None:
            self.status.set('三维预览窗口已打开，修改配方会自动同步。');self.sync_preview3d();return
        try:
            state=self.preview3d_state();client=self.selected_client()
        except ValueError as error:messagebox.showerror('暂时无法预览',str(error),parent=self);return
        from .preview3d import Session
        project=dict(self.project);project['lights']=[dict(x) for x in self.project['lights']]
        def work():
            session=Session(project,client);session.update(state)
            if self._closing:session.close()
            return session
        def done(session):
            if self.preview3d:self.preview3d.close()
            self.preview3d=session
            self.status.set('三维窗口正在读取整车。首次加载建立缓存，修改参数自动同步。')
            if self._three_after is not None:self.after_cancel(self._three_after)
            self.poll_preview3d()
        self.job(work,done)

    def schedule_preview3d(self):
        if self._closing or not self.preview3d or self.preview3d.closed:return
        if self._three_update_after is not None:self.after_cancel(self._three_update_after)
        self._three_update_after=self.after(180,self.sync_preview3d)

    def sync_preview3d(self):
        if self._three_update_after is not None:self.after_cancel(self._three_update_after)
        self._three_update_after=None
        if not self.preview3d or self.preview3d.closed:return
        try:self.preview3d.update(self.preview3d_state())
        except ValueError as error:self.status.set('三维预览保留上次有效配方：'+str(error))

    def poll_preview3d(self):
        self._three_after=None;session=self.preview3d
        if self._closing or not session:return
        if session.viewer and session.viewer.poll() is not None:
            code=session.viewer.returncode;session.close();self.preview3d=None
            self.status.set('三维窗口已关闭。' if code==0 else '三维窗口未能启动或已退出；请检查 WebView2 Runtime，二维预览仍可使用。')
            return
        try:
            while True:
                event=session.events.get_nowait()
                if event['type']=='performance':
                    value=next((name for name,key in preview3d_preferences.PROFILES.items() if key==event['value']),None)
                    if value and self.performance.get()!=value:self.performance.set(value)
                    continue
                if event['type']=='bodyselect':
                    self.open_area_dialog(event['selection'],session)
                    continue
                if event['type']!='select' or event['id'] not in self.records:continue
                identifier=event['id']
                if event['subtract']:self.picked.discard(identifier)
                elif event['add']:self.picked.add(identifier)
                else:self.picked={identifier}
                self.active=self.records[identifier] if identifier in self.picked else None
                self.sync_pick()
        except queue.Empty:pass
        self._three_after=self.after(150,self.poll_preview3d)

    def open_area_dialog(self, selection, session):
        if self.busy or not self.project:return
        info=session.read_json('body.json')
        if not info:return
        dialog=tk.Toplevel(self);prepare_dialog(dialog,'框选区域制作');dialog.transient(self)
        box=ttk.Frame(dialog,padding=20,style='Card.TFrame');box.pack(fill='both',expand=True)
        count=sum(len(g['triangles']) for g in selection['groups'])
        ttk.Label(box,text='已选 %d 个三角面'%count,style='Section.TLabel').pack(anchor='w')
        ttk.Label(box,text='选区包含屏幕投影内的遮挡面。请先旋转模型核对高亮；贴图和灯效分别生成待实测包。',wraplength=500).pack(anchor='w',pady=10)
        x=tk.StringVar(value='0.5');y=tk.StringVar(value='0.5');scale=tk.StringVar(value='1.0')
        row=ttk.Frame(box,style='Card.TFrame');row.pack(anchor='w',pady=5)
        for label,var,help_name in [('横向位置 0～1',x,'区域横向位置'),('纵向位置 0～1',y,'区域纵向位置'),('缩放',scale,'区域图片缩放')]:
            self.hint(ttk.Label(row,text=label),help_name).pack(side='left');self.hint(ttk.Entry(row,textvariable=var,width=6),help_name).pack(side='left',padx=(4,12))
        ttk.Label(box,text='图片按选区 UV 边界放置；位置与缩放用于调整图片。只支持同一张车体 AM 贴图，所显示模型的 UV 共用时会停止。其他 LOD、未显示外观及压缩边缘仍需游戏内检查。',wraplength=500).pack(anchor='w',pady=8)
        def paint():
            image=filedialog.askopenfilename(parent=dialog,title='选择贴花图片',filetypes=[('图片','*.png *.jpg *.jpeg *.webp')])
            if not image:return
            try:
                px,py,zoom=float(x.get()),float(y.get()),float(scale.get());client=self.selected_client()
            except ValueError as error:messagebox.showerror('参数有误',str(error),parent=dialog);return
            from . import area_selection
            project=self.project_snapshot();baseline=self.baseline.get();title=self.title_value.get();body=info['scene'];folder=info['folder']
            dialog.destroy()
            self.job(lambda: area_selection.paint_texture(project,selection,body,folder,image,client,ROOT/'result/框选制作',title,px,py,zoom,baseline),
                     lambda result:self.area_built(result,'贴图'))
        def light():
            try:client=self.selected_client();recipe=self.read_form()
            except ValueError as error:messagebox.showerror('参数有误',str(error),parent=dialog);return
            if self.project.get('recovery'):
                messagebox.showerror('需要原始涂装','请从原始涂装包开始，避免与旧灯效脚本叠加。',parent=dialog);return
            from . import area_selection
            project=self.project_snapshot();project['recipe']=recipe;project['baseline_user_confirmed']=self.baseline.get();title=self.title_value.get()
            def work():
                project['lights']=area_selection.extract_rigid_lights(project,selection,client=client)
                return engine.build(project,client,ROOT/'result/框选制作',title,self.log,embed_recoverable=False)
            dialog.destroy();self.job(work,lambda result:self.area_built(result,'灯效'))
        row=ttk.Frame(box,style='Card.TFrame');row.pack(anchor='w',pady=8)
        self.hint(ttk.Button(row,text='选择图片并生成贴图包',command=paint),'选择图片并生成贴图包').pack(side='left',padx=(0,8))
        self.hint(ttk.Button(row,text='按当前配方生成独立灯效',command=light,style='Accent.TButton'),'按当前配方生成独立灯效').pack(side='left')

    def area_built(self,result,kind):
        target,report=result;self.last_output=target
        self.status.set('框选%s待测包已生成：%s；游戏内尚未验收。'%(kind,target))
        messagebox.showinfo('待实测包已生成','%s\n\nSHA256：%s\n\n请先在实际客户端检查整车加载与选区效果。'%(target,report['artifact']['sha256']),parent=self)

    def preview_lights(self):
        if not self.project or not self.project['lights']:return []
        if self.preview_scope.get()=='全部灯面':return list(self.project['lights'])
        active=self.active or next((x for x in self.project['lights'] if x['supported']),self.project['lights'][0])
        return [x for x in self.project['lights'] if x['visual']==active['visual']]

    def preview_sample_limit(self,lights):
        limit=light_select.face_sample_limit(len(lights))
        if self.preview_mode.get()=='实时灯效' and lights:
            limit=min(limit,max(2,1000//len(lights)))
        return limit

    def live_seconds(self):
        return self._live_elapsed+(0 if self._live_paused else time.perf_counter()-self._live_start)

    def change_preview_mode(self,event=None):
        if self._live_after is not None:self.after_cancel(self._live_after);self._live_after=None
        if self._live_edit_after is not None:self.after_cancel(self._live_edit_after);self._live_edit_after=None
        self._live_elapsed=0.;self._live_start=time.perf_counter()
        self._live_paused=False;self.live_play_text.set('暂停')
        self.preview_caption.set('灯效模拟 · 仅勾选灯面' if self.preview_mode.get()=='实时灯效' else 'Shift 加选 · Ctrl 减选 · Alt 整模型')
        self.draw_preview()
        if self.preview_mode.get()=='实时灯效':self.live_tick()

    def pause_live(self):
        if self.preview_mode.get()!='实时灯效':return
        self._live_elapsed=self.live_seconds();self._live_start=time.perf_counter()
        self._live_paused=not self._live_paused
        self.live_play_text.set('播放' if self._live_paused else '暂停')

    def restart_live(self):
        self._live_elapsed=0.;self._live_start=time.perf_counter();self.paint_live()

    def preview_form_changed(self,*args):
        if self._closing:return
        self.schedule_preview3d()
        if self.preview_mode.get()!='实时灯效':return
        if self._live_edit_after is not None:self.after_cancel(self._live_edit_after)
        self._live_edit_after=self.after(200,self.refresh_live_form)

    def refresh_live_form(self):
        if self._live_edit_after is not None:self.after_cancel(self._live_edit_after)
        self._live_edit_after=None
        self.draw_preview()

    def request_live_plan(self):
        if not self.project:return
        try:
            global_recipe,lights=self.effective_recipes()
            key=(id(self.project),json.dumps(global_recipe,sort_keys=True),
                 tuple((x['id'],bool(x.get('selected')),json.dumps(x.get('配方'),sort_keys=True)) for x in lights))
        except (ValueError,TypeError) as error:
            self._live_error=True;self._live_key=None;self._live_pending=None
            self.live_note.set('参数未完成，保留上次有效模拟：'+str(error))
            self.preview_caption.set('参数未完成 · 悬停查看原因');return
        self._live_error=False
        note='模拟 · 仅勾选的可制作灯面发光；原生呼吸、贴图、泛光及遮挡以游戏为准。'
        if self.edit_scope.get() in ('套选模型','套选灯面'):note='模拟套选草稿 · 生成前需应用；其余灯面使用各自配方。'
        self.live_note.set(note)
        if any(x.get('sampled') for x in self._live_plan):
            self.live_note.set(note+' 密集灯面已抽样，分段相位和位置为近似显示；导出仍保留完整几何。')
        self.preview_caption.set('模拟套选草稿 · 生成前需应用' if self.edit_scope.get() in ('套选模型','套选灯面') else '灯效模拟 · 仅勾选灯面')
        if key!=self._live_key:
            self._live_key=key;self._live_plan=[];self._live_pending=(key,lights,copy.deepcopy(global_recipe))
            self.live_note.set('正在准备灯段模拟…')
            self.preview_caption.set('正在准备灯段模拟…')
        self.start_live_worker()

    def start_live_worker(self):
        if self._live_worker or self._live_pending is None:return
        key,lights,recipe=self._live_pending;self._live_pending=None;self._live_worker=True
        def work():
            try:result=light_preview.prepare(lights,recipe);error=None
            except Exception as exc:result=[];error=str(exc)
            self._live_results.put((key,result,error))
        threading.Thread(target=work,daemon=True).start()

    def live_tick(self):
        self._live_after=None
        if self._closing or self.preview_mode.get()!='实时灯效':return
        try:
            while True:
                key,plan,error=self._live_results.get_nowait();self._live_worker=False
                if key==self._live_key:
                    self._live_plan=plan
                    self.draw_preview()
                    if error:
                        self._live_error=True;self.live_note.set('无法模拟：'+error);self.preview_caption.set('无法模拟 · 悬停查看原因')
                    elif not plan:
                        self.live_note.set('请先勾选可制作灯面，再查看实时效果。');self.preview_caption.set('请先勾选可制作灯面')
        except queue.Empty:pass
        self.start_live_worker();self.paint_live()
        self._live_after=self.after(50,self.live_tick)

    def paint_live(self):
        seconds=self.live_seconds()
        for band,core,halo in self._live_tags:
            color,glow=light_preview.colors(seconds,band)
            for tag,value in ((core,color),(halo,glow)):
                if self._live_last_colors.get(tag)!=value:
                    self.canvas.itemconfigure(tag,fill=value);self._live_last_colors[tag]=value

    def draw_live_overlay(self,view):
        visible={x['visual'] for x in self._preview_lights};self._live_tags=[];self._live_last_colors={}
        for index,band in enumerate(self._live_plan):
            if not band['visuals'].intersection(visible):continue
            core='live_core_%d'%index;halo='live_halo_%d'%index
            for pane in view.panes:
                screen=view.screen(band['points'],pane);screen=screen[view.visible(screen,pane)]
                for x,y in screen:
                    # Clip halos too, so neighbouring orthographic panes stay separate.
                    x0=max(pane['left']+2,x-3);x1=min(pane['left']+pane['width']-2,x+3)
                    self.canvas.create_oval(x0,max(32,y-3),x1,min(view.height-2,y+3),fill='#101825',outline='',tags=halo)
                    self.canvas.create_oval(x-1.2,y-1.2,x+1.2,y+1.2,fill='#ffffff',outline='',tags=core)
            self._live_tags.append((band,core,halo))
        self.paint_live()

    def draw_preview(self):
        self.schedule_preview3d()
        live=self.preview_mode.get()=='实时灯效'
        self.canvas.configure(bg='#0c111b' if live else '#f7f9fc')
        self._live_tags=[]
        self.canvas.delete('all');w=max(self.canvas.winfo_width(),1);h=max(self.canvas.winfo_height(),1)
        if w<10:w=600
        if h<64:h=220
        self._preview_view=None;self._preview_lights=[]
        if not self.project:
            self.canvas.create_text(w/2,h/2,text='提取后可查看灯面位置',fill='#737d8c');return
        lights=self.preview_lights()
        if not lights:
            self.canvas.create_text(w/2,h/2,text='没有可显示的灯面',fill='#737d8c');return
        keys=tuple(x['id'] for x in lights)
        if self._preview_keys is not None and self._preview_keys!=keys:
            self._preview_zoom=1.0;self._preview_pan=np.zeros((3,2));self.zoom_text.set('100%')
        self._preview_keys=keys
        view=light_select.View(lights,w,h,self._preview_zoom,self._preview_pan);self._preview_view=view;self._preview_lights=lights
        limit=self.preview_sample_limit(lights)
        for pane in view.panes:
            left=pane['left'];width=pane['width']
            for step in range(1,5):
                x=left+width*step/5
                self.canvas.create_line(x,32,x,h,fill='#202a39' if live else '#e6eaf0')
                y=32+(h-32)*step/5
                self.canvas.create_line(left,y,left+width,y,fill='#202a39' if live else '#e6eaf0')
            if left:self.canvas.create_line(left,0,left,h,fill='#d9dfe7')
            self.canvas.create_text(left+width/2,17,text=pane['label'],fill='#697586',font=('Microsoft YaHei UI',9))
        for light in lights:
            if light is self.active:col='#f09318'
            elif light['id'] in self.picked:col='#007aff'
            elif light.get('selected'):col='#009d92'
            else:col='#384355' if live else '#9ba6b4'
            points=np.asarray(light['_preview'],dtype=float);step=max(1,len(points)//limit);points=points[::step]
            for pane in view.panes:
                screen=view.screen(points,pane)
                screen=screen[view.visible(screen,pane)]
                for x,y in screen:
                    self.canvas.create_oval(x-1.4,y-1.4,x+1.4,y+1.4,fill=col if not live else '',outline=col if live else '')
        if live:self.request_live_plan();self.draw_live_overlay(view)
        self.draw_marquee()

    def zoom_preview(self,factor,x=None,y=None):
        if self.busy or self._preview_view is None:return
        self.hover_help.hide()
        view=self._preview_view
        self._preview_zoom=view.zoom_by(factor,x,y)
        self._preview_pan=view.pan.copy()
        self.zoom_text.set('%g%%'%round(self._preview_zoom*100,1))
        self.draw_preview()

    def reset_preview(self):
        self._preview_zoom=1.0;self._preview_pan=np.zeros((3,2));self._pan_origin=None
        self.zoom_text.set('100%');self.draw_preview()

    def on_preview_wheel(self,event):
        self.hover_help.hide()
        if self.busy:return 'break'
        delta=getattr(event,'delta',0)
        if delta:self.zoom_preview(1.2**max(-10,min(10,delta/120)),event.x,event.y)
        return 'break'

    def on_pan_press(self,event):
        if self.busy or self._preview_view is None:return
        self.hover_help.hide()
        self._pan_origin=(event.x,event.y,self._preview_view.pane_at(event.x)['index'])
        return 'break'

    def on_pan_drag(self,event):
        if self._pan_origin is None:return
        x,y,index=self._pan_origin
        self._preview_pan[index]+=np.array([event.x-x,event.y-y])
        self._pan_origin=(event.x,event.y,index)
        self.draw_preview()
        return 'break'

    def on_pan_release(self,event):
        self._pan_origin=None
        return 'break'

    def draw_marquee(self):
        self.canvas.delete('marquee')
        if not self._drag_rect:return
        x0,y0,x1,y1=light_select.normalize_rect(self._drag_rect)
        self.canvas.create_rectangle(x0,y0,x1,y1,outline='#007aff',dash=(4,2),width=1,tags='marquee')

    def on_canvas_press(self,event):
        if self.busy or not self.project:return
        self._drag_origin=(event.x,event.y);self._drag_rect=None

    def on_canvas_drag(self,event):
        if not self._drag_origin:return
        self._drag_rect=(self._drag_origin[0],self._drag_origin[1],event.x,event.y)
        self.draw_marquee()

    def on_canvas_release(self,event):
        if not self._drag_origin or not self.project:return
        origin=self._drag_origin;rect=(origin[0],origin[1],event.x,event.y)
        self._drag_origin=None;self._drag_rect=None;self.canvas.delete('marquee')
        if light_select.rect_too_small(rect):
            self.pick_at(origin[0],origin[1]);return
        self.apply_marquee(rect,event.state)

    def pick_at(self,x,y):
        view=self._preview_view;lights=self._preview_lights
        if not view:return
        hit=view.nearest(lights,x,y,limit=self.preview_sample_limit(lights))
        self.active=self.records.get(hit) if hit else None
        self.picked={hit} if hit else set()
        self.sync_pick()

    def apply_marquee(self,rect,state=0):
        view=self._preview_view;lights=self._preview_lights
        if not view:return
        shift=bool(state&0x1);control=bool(state&0x4);alt=bool(state&(0x8|0x20000))
        hits=view.hit(lights,rect,limit=self.preview_sample_limit(lights))
        if not hits:
            if not (shift or control):
                self.picked=set();self.active=None;self.sync_pick()
                self.status.set('方框内没有灯面，已清除套选。')
            return
        if alt:
            keys=light_select.expand_to_models(lights,hits)
            hits=[x['id'] for x in lights if x['id'] in keys]
        mode=light_select.drag_mode(shift=shift,control=control)
        merged=light_select.merge(self.picked,hits,mode)
        self.picked=merged
        if mode!='subtract':self.active=self.records.get(hits[-1],self.active)
        elif self.active and self.active['id'] not in merged:self.active=None
        self.sync_pick()
        scope='整模型' if alt else '灯面'
        self.status.set('套选 %d 块灯面 / %d 个模型（按%s）。'%(len(self.picked),light_select.model_count(self.project['lights'],self.picked),scope))

    def pick_scope_all(self):
        if self.busy or not self.project:return
        lights=[x for x in self.preview_lights() if x['supported']]
        self.picked={x['id'] for x in lights}
        self.active=lights[-1] if lights else None
        self.sync_pick()
        self.status.set('已套选当前显示范围内的 %d 块可制作灯面。'%len(lights))

    def pick_models(self):
        if self.busy or not self.project:return
        if not self.picked:self.status.set('先在预览里套选灯面，再按整模型扩选。');return
        self.picked=light_select.expand_to_models(self.project['lights'],self.picked)
        self.sync_pick()
        self.status.set('已按模型扩选到 %d 块灯面 / %d 个模型。'%(len(self.picked),light_select.model_count(self.project['lights'],self.picked)))

    def pick_clear(self):
        self.picked=set();self.active=None;self.sync_pick()
        self.status.set('已清除套选；已勾选和已设配方都不受影响。')

    def mark_picked(self,value):
        if self.busy or not self.project:return
        lights=[x for x in self.picked_lights() if x['supported']]
        if not lights:self.status.set('先套选可制作灯面，再勾选或取消。');return
        for light in lights:
            light['selected']=bool(value);self.refresh_item(light)
        self.update_count();self.draw_preview()
        self.status.set(('已勾选 ' if value else '已取消勾选 ')+'%d 块套选灯面。'%len(lights))

    def keep_only_picked(self):
        if self.busy or not self.project:return
        lights=[x for x in self.picked_lights() if x['supported']]
        if not lights:self.status.set('先套选可制作灯面，再只保留它们。');return
        if not messagebox.askyesno('只保留套选','取消勾选套选之外的其它灯面？',parent=self):return
        for light in self.project['lights']:
            light['selected']=light['supported'] and light['id'] in self.picked
            self.refresh_item(light)
        self.update_count();self.draw_preview()
        self.status.set('已只保留套选的 %d 块灯面。'%len(lights))

    def apply_recipe_to_picked(self):
        """Apply the current draft to the selected faces or whole models."""
        if self.busy or not self.project:return
        lights=[x for x in self.picked_lights() if x['supported']]
        if not lights:self.status.set('先在预览里套选灯面或模型，再一起设置。');return
        try:cfg=self.read_form()
        except ValueError as error:messagebox.showerror('配置有误',str(error));return
        keys={light_select.model_key(x) for x in lights}
        scope='套选灯面' if self.edit_scope.get()=='套选灯面' else '套选模型'
        targets=self.draft_targets(scope,supported_only=True)
        faces=[x for x in self.project['lights'] if x['supported'] and x['id'] in targets]
        for light in faces:
            light['配方']=copy.deepcopy(cfg);self.refresh_item(light)
        # This action explicitly means local application, even when invoked from
        # the global tab. Save/build must never promote its form into project['recipe'].
        scope='套选灯面' if self.edit_scope.get()=='套选灯面' else '套选模型'
        self.edit_scope.set(scope);self._editor_scope=scope
        self._local_form_baseline=copy.deepcopy(cfg)
        self.active=self.records.get(lights[-1]['id'],self.active)
        self.sync_pick()
        self.status.set(('已应用到 %d 块灯面（含对应外观的重复灯面）。'%len(faces) if scope=='套选灯面' else '已应用到 %d 个模型（%d 块灯面，含对应外观）。'%(len(keys),len(faces)))+'全局配方保持不变。')

    def clear_recipe_on_picked(self):
        if self.busy or not self.project:return
        lights=self.picked_lights()
        if not lights:self.status.set('先在预览里套选灯面或模型，再恢复全局配方。');return
        keys={light_select.model_key(x) for x in lights}
        base=lights if self.edit_scope.get()=='套选灯面' else [x for x in self.project['lights'] if light_select.model_key(x) in keys]
        targets=self.with_variant_aliases(x['id'] for x in base)
        faces=[x for x in self.project['lights'] if x['id'] in targets and engine.override_recipe(x)]
        if not faces:
            self.status.set('这些模型本来就在使用全局配方。');return
        for light in faces:light.pop('配方',None);self.refresh_item(light)
        if self.edit_scope.get() in ('套选模型','套选灯面'):
            self.fill_recipe(self.project['recipe'])
            self._local_form_baseline=copy.deepcopy(self.read_form())
        self.sync_pick()
        self.status.set('已让 %d 块灯面回到全局配方。'%len(faces))

    def apply_preset(self,event=None):
        record=self.preset_library.get(self.preset.get())
        if record:
            self.fill_recipe(record['配方']);self.status.set(record['说明'])

    def recipe_scope_report(self):
        """Selected faces whose own recipe shadows the global one, plus kept models."""
        if not self.project:return [],[],'流水呼吸',0
        local=[x for x in self.project['lights'] if x.get('selected') and x['supported'] and engine.override_recipe(x)]
        global_mode=self.project['recipe'].get('效果模式','流水呼吸')
        def effective(raw):
            return {k:v for k,v in engine.light_recipe.validate_config(raw).items() if k!='raw'}
        global_values=effective(self.project['recipe'])
        differing=[x for x in local if effective(engine.override_recipe(x))!=global_values]
        retained=sum(1 for x in self.project['lights'] if x.get('recovered_model') and not x.get('selected'))
        return local,differing,global_mode,retained

    def confirm_recipe_scope(self):
        """Warn before a build whose result cannot follow the edited global recipe.

        v2.1.0 let a global edit look applied while selected faces kept their own
        recipe and unselected recovered models kept the finished package effect;
        that is what made every adjustment still breathe.
        """
        local,differing,global_mode,retained=self.recipe_scope_report()
        if not differing and not retained:return True
        lines=[]
        if differing:
            modes=sorted({(engine.override_recipe(x) or {}).get('效果模式','流水呼吸') for x in differing})
            lines.append('%d 块已勾选灯面的独立配方与当前全局参数不同（全局模式：%s；独立模式：%s）。\n即使模式相同，暗相、颜色或周期也可能不同；改全局配方或换预设不会影响这些灯面。'
                         % (len(differing),global_mode,'、'.join(modes)))
        if retained:
            lines.append('%d 个未勾选的成品恢复模型会保留原包效果，配方改动不会改变它们。'%retained)
        lines.append('继续生成？想统一效果请先点“全部改回全局”。')
        return messagebox.askyesno('配方范围提醒','\n\n'.join(lines),parent=self)

    def clear_all_recipe_overrides(self):
        """Return every face to the global recipe so one edit really covers all."""
        if self.busy or not self.project:return
        faces=[x for x in self.project['lights'] if x['supported'] and engine.override_recipe(x)]
        if not faces:
            self.status.set('所有灯面本来就在使用全局配方。');return
        try:
            current=self.read_form()
            if self.edit_scope.get()!='全局配方' and (self._local_form_baseline is None or current!=self._local_form_baseline):
                raise ValueError('局部参数尚未应用，请先应用到套选，或放弃草稿，再全部改回全局。')
        except ValueError as error:
            messagebox.showerror('参数未保存',str(error),parent=self);return
        if not messagebox.askyesno('全部改回全局','清除 %d 块灯面的独立配方？它们会改用当前全局配方。'%len(faces),parent=self):return
        # The global form is a draft until save/build. Commit it before loading
        # project['recipe'], otherwise this button restores the old Pulse recipe.
        if self.edit_scope.get()=='全局配方':self.commit_global_form(current)
        for light in faces:light.pop('配方',None);self.refresh_item(light)
        self.edit_scope.set('全局配方');self._editor_scope='全局配方'
        self.fill_recipe(self.project['recipe'])
        self._global_form_baseline=copy.deepcopy(self.read_form())
        self._local_form_baseline=None
        self.sync_pick()
        self.status.set('已让 %d 块灯面改用全局配方；现在修改全局配方会作用到全部灯面。'%len(faces))

    def open_palette(self):
        if self.busy:return
        from .light_palette import PaletteDialog
        try:
            return PaletteDialog(self,self.colors.get(),self.apply_palette)
        except ValueError as error:messagebox.showerror('颜色格式有误',str(error),parent=self)

    def apply_palette(self,value):
        self.colors.set(value)
        self.status.set('颜色已填入当前表单；局部配方仍需点击应用到套选。')

    def read_form(self):
        colors=[x.strip() for x in self.colors.get().replace('，',',').split(',') if x.strip()]
        cfg={'颜色':[{'名称':'颜色%d'%(i+1),'RGB':c} for i,c in enumerate(colors)],'每色秒数':float(self.step.get()),'呼吸周期秒数':float(self.breath.get()),'峰值倍率':float(self.peak.get()),'暗相系数':float(self.low.get()),'每米延迟秒数':float(self.delay.get()),'流水方向':self.direction.get(),'效果模式':self.effect_mode.get(),'亮灯比例':float(self.duty.get())}
        enabled=self.dimming.get() and self.effect_mode.get() not in engine.light_recipe.COLOR_ONLY_MODES
        if enabled != (self.effect_mode.get() not in engine.light_recipe.COLOR_ONLY_MODES):
            cfg['启用明暗变化']=enabled
        # Omit the default so projects saved before v2.1 keep identical recipes.
        if self.color_curve.get()=='匀速无缝':cfg['换色曲线']='匀速'
        engine.light_recipe.validate_config(cfg)
        return cfg

    def sync_recipe(self):
        if not self.project:raise ValueError('请先提取涂装或打开灯光工程')
        cfg=self.read_form()
        if self.edit_scope.get()=='全局配方':
            self.commit_global_form(cfg)
        elif self._local_form_baseline is None or cfg!=self._local_form_baseline:
            raise ValueError('局部参数尚未应用，请先应用到套选，或放弃草稿，再保存或生成。')
        self.project['baseline_user_confirmed']=self.baseline.get()

    def save_current_preset(self):
        try:cfg=self.read_form()
        except ValueError as e:messagebox.showerror('配置有误',str(e));return
        name=simpledialog.askstring('保存为预设','输入新名称；使用已有名称可以修改对应预设。',initialvalue=self.preset.get() if self.preset.get() in self.preset_library else '我的预设',parent=self)
        if name is None:return
        name=name.strip()
        if name in self.preset_library and not messagebox.askyesno('修改已有预设','覆盖“'+name+'”的配方？旧库会保留一份 .bak 备份。',parent=self):return
        description=simpledialog.askstring('预设说明','输入说明（可留空）：',initialvalue=self.preset_library.get(name,{}).get('说明',''),parent=self)
        if description is None:return
        records=copy.deepcopy(self.preset_library);records[name]={'说明':description,'配方':cfg}
        try:presets.save(records)
        except (ValueError,OSError) as e:messagebox.showerror('未保存',str(e));return
        self.preset_library=records;self.preset_combo.configure(values=list(records));self.preset.set(name)
        self.status.set('预设已保存，下次启动仍可选择：'+name)

    def manage_presets(self):
        dialog=tk.Toplevel(self);prepare_dialog(dialog,'灯效预设');dialog.geometry('760x520');dialog.minsize(700,440);dialog.transient(self);dialog.grab_set()
        box=ttk.Frame(dialog,padding=18,style='Backdrop.TFrame');box.pack(fill='both',expand=True)
        ttk.Label(box,text='灯效预设库',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(box,text='加载到主窗口后修改参数，再点“保存为预设”。也可导入、导出或直接编辑 JSON。',wraplength=660).pack(anchor='w')
        # Reserve both action rows before the expanding list. Previously a
        # compact/high-DPI dialog could hide its import/export/close controls.
        footer=ttk.Frame(box);footer.pack(side='bottom',fill='x',pady=(12,0))
        listing=tk.Listbox(box,height=12,bg='white',fg='#1d1d1f',selectbackground='#e5f0ff',
                          selectforeground='#005ac4',relief='flat',highlightbackground='#e5e5ea',
                          highlightcolor='#007aff',font=('Microsoft YaHei UI',10))
        style_listbox(listing);listing.pack(fill='both',expand=True,pady=10)
        def preset_help(event):
            index=listing.nearest(event.y)
            return light_help.option('预设',listing.get(index),self) if listing.size() else light_help.topic('预设列表')
        self.hover_help.attach(listing,preset_help)
        description=tk.StringVar();ttk.Label(footer,textvariable=description,wraplength=660,style='Muted.TLabel').pack(fill='x',pady=(0,8))
        def refresh():
            listing.delete(0,'end')
            for name in self.preset_library:listing.insert('end',name)
        def chosen():return listing.get(listing.curselection()[0]) if listing.curselection() else None
        def display(event=None):
            name=chosen();description.set(self.preset_library[name]['说明'] if name else '')
        listing.bind('<<ListboxSelect>>',display)
        def load():
            name=chosen()
            if name:self.preset.set(name);self.apply_preset();dialog.destroy()
        def imported():
            path=filedialog.askopenfilename(parent=dialog,filetypes=[('灯效预设','*.json')])
            if not path:return
            try:
                incoming=presets.import_file(path)
                collisions=set(incoming)&set(self.preset_library)
                if collisions and not messagebox.askyesno('同名预设','导入后将覆盖 %d 个同名预设，继续？'%len(collisions),parent=dialog):return
                merged={**self.preset_library,**incoming};presets.save(merged)
                self.preset_library=merged;self.preset_combo.configure(values=list(merged));refresh()
            except (ValueError,OSError) as e:messagebox.showerror('导入失败',str(e),parent=dialog)
        def exported():
            name=chosen()
            if not name:return
            path=filedialog.asksaveasfilename(parent=dialog,defaultextension='.json',initialfile='灯效预设.json',filetypes=[('灯效预设','*.json')])
            if path:
                try:presets.export_file({name:self.preset_library[name]},path)
                except (ValueError,OSError) as e:messagebox.showerror('导出失败',str(e),parent=dialog)
        def removed():
            name=chosen()
            if not name or not messagebox.askyesno('删除预设','删除“'+name+'”？',parent=dialog):return
            merged=copy.deepcopy(self.preset_library);del merged[name]
            try:presets.save(merged)
            except (ValueError,OSError) as e:messagebox.showerror('未删除',str(e),parent=dialog);return
            self.preset_library=merged;self.preset_combo.configure(values=list(merged));refresh()
        def reset():
            if not messagebox.askyesno('恢复内置预设','恢复全部内置配方，自定义名称的预设保留。',parent=dialog):return
            merged={**self.preset_library,**presets.defaults()}
            try:presets.save(merged)
            except (ValueError,OSError) as e:messagebox.showerror('未恢复',str(e),parent=dialog);return
            self.preset_library=merged;self.preset_combo.configure(values=list(merged));refresh()
        def edit_file():
            try:presets.save(self.preset_library);os.startfile(presets.LIBRARY_PATH)
            except (ValueError,OSError) as e:messagebox.showerror('无法打开',str(e),parent=dialog)
        def reload_file():
            try:records=presets.load()
            except (ValueError,OSError) as e:messagebox.showerror('格式有误',str(e),parent=dialog);return
            self.preset_library=presets.with_new_presets(records);self.preset_combo.configure(values=list(self.preset_library));refresh()
        row=ttk.Frame(footer);row.pack(fill='x',pady=(0,8))
        for label,action in [('加载并修改',load),('导入',imported),('导出选中',exported),('删除',removed),('恢复内置',reset)]:
            b=ttk.Button(row,text=label,command=action);self.hint(b,label);b.pack(side='left',padx=3)
        row=ttk.Frame(footer);row.pack(fill='x')
        for label,action in [('打开预设 JSON',edit_file),('重新读取 JSON',reload_file),('关闭',dialog.destroy)]:
            b=ttk.Button(row,text=label,command=action);self.hint(b,label);b.pack(side='left',padx=3)
        refresh()

    def save_project(self):
        if self.busy:return
        try:self.sync_recipe()
        except ValueError as e:messagebox.showerror('配置有误',str(e));return
        self.project['embed_recoverable']=self.embed_recoverable.get()
        p=filedialog.asksaveasfilename(defaultextension='.wotlights',filetypes=[('灯光工程','*.wotlights')],initialfile='车辆灯光工程.wotlights')
        if p:
            snapshot=self.project_snapshot()
            self.job(lambda:engine.save_project(snapshot,p),lambda _:self.status.set('灯光工程已保存：'+p))

    def build(self):
        if self.busy:return
        try:
            self.sync_recipe()
            client=str(engine.resolve_client_root(self.client.get()))
        except ValueError as e:messagebox.showerror('配置有误',str(e));return
        if not self.confirm_recipe_scope():return
        self.client.set(client);title=self.title_value.get()
        install=self.auto_install.get()
        auto_bundle=self.auto_bundle.get();output_folder=self.output_folder.get()
        self.project['embed_recoverable']=self.embed_recoverable.get()
        snapshot=self.project_snapshot()
        def work():
            target,report=engine.build(snapshot,client,Path(output_folder),title,self.log)
            if auto_bundle:
                from . import light_delivery
                report['delivery']=light_delivery.bundle(target,report)
            installation=None;error=None
            if install:
                try:installation=support.install_mod(target,client,self.log)
                except Exception as e:error=str(e)
            return target,report,installation,error
        self.job(work,self.built)

    def merge_packages(self):
        if self.busy:return
        try:client=self.selected_client()
        except ValueError as error:messagebox.showerror('游戏目录有误',str(error),parent=self);return
        paths=filedialog.askopenfilenames(title='选择至少两个同车灯效成品包',filetypes=[('WOT 涂装','*.wotmod')])
        if not paths:return
        if len(paths)<2:messagebox.showerror('选择不足','请同时选择至少两个包。',parent=self);return
        from . import light_merge
        work=self.work_dir();title=self.title_value.get()+' 合并'
        # The current checkbox can refer to a different imported project.
        # Do not transfer that confirmation to the merged inputs.
        self.job(lambda:light_merge.build(paths,client,ROOT/'result/灯效合并',work,title,False,self.log),self.built)

    def built(self,result):
        target,report,installation,error=result;self.last_output=target
        if installation:
            self.last_install=installation['backup']
            text='已生成并安装待测包：'+installation['target']+'\n已备份冲突资源，可用“恢复上次安装”撤销。'
        else:text='已生成待测包：'+str(target)
        if report.get('delivery'):text+='\n已自动打包 ZIP：'+report['delivery']['path']
        if error:
            text+='\n\n自动安装未完成：'+error+'\n生成的涂装包仍保存在产物文件夹。'
        if report.get('embedded_project',{}).get('enabled'):
            size=report['embedded_project']['bytes']/1024/1024
            text+='\n已嵌入可恢复工程（约 %.1f MB）；以后可用“导入涂装 / 成品”恢复生成前的工程状态。'%size
        self.status.set(text+'。游戏效果待实测。')
        messagebox.showinfo('制作完成',text+'\n\n请检查整车加载、换色、随动和开镜恢复；安装成功不代表游戏验收通过。')

    def selected_client(self):
        root=str(engine.resolve_client_root(self.client.get()));self.client.set(root);return root

    def install_existing(self):
        try:client=self.selected_client()
        except ValueError as e:messagebox.showerror('游戏目录有误',str(e));return
        p=filedialog.askopenfilename(title='选择制作器生成的待测灯效包（先退出游戏）',filetypes=[('灯效模组','*.wotmod')])
        if not p:return
        self.job(lambda:support.install_mod(p,client,self.log),self.installed)

    def installed(self,result):
        self.last_install=result['backup']
        self.last_output=Path(result['source'])
        self.status.set('已安装待测包：'+result['target'])
        messagebox.showinfo('安装完成','已安装到：'+result['target']+'\n备份位置：'+str(Path(result['backup']).parent)+'\n\n测试开始已自动标记。退出游戏后可用“恢复上次安装”撤销。')

    def restore_previous(self):
        try:
            client=self.selected_client();backup=support.latest_install(client)
        except ValueError as e:messagebox.showerror('无法恢复',str(e));return
        self.job(lambda:support.restore_install(backup),lambda _:self.restored())

    def restored(self):
        self.last_install=None;self.status.set('已撤销上次安装，并恢复安装前备份。')
        messagebox.showinfo('已恢复','已撤销上次安装；停用的生成包保留在备份目录中。')

    def mark_test(self):
        try:client=self.selected_client()
        except ValueError as e:messagebox.showerror('游戏目录有误',str(e));return
        self.job(lambda:support.mark_test(client),lambda _:self.status.set('已标记测试开始。现在可进入游戏测试，结束后点击“提取游戏报错日志”。'))

    def export_game_logs(self):
        try:client=self.selected_client()
        except ValueError as e:messagebox.showerror('游戏目录有误',str(e));return
        since=self.log_since_mark.get();package=self.last_output
        self.job(lambda:support.export_logs(client=client,since_mark=since,package=package),self.logs_exported)

    def export_selected_logs(self):
        files=filedialog.askopenfilenames(title='选择 game.log 或 python.log（支持其他电脑发来的日志）',filetypes=[('游戏日志','*.log')])
        if not files:return
        package=self.last_output
        self.job(lambda:support.export_logs(files=files,since_mark=False,package=package),self.logs_exported)

    def logs_exported(self,result):
        path,summary=result
        self.status.set('已提取日志：'+str(path))
        messagebox.showinfo('日志已提取','已生成过滤敏感信息的日志摘录和排查摘要：\n'+str(path)+'\n\n这是本地文件，可以手动发给排查人员。')
        os.startfile(path.parent)

    def show_output(self):
        path=self.last_output.parent if self.last_output else Path(self.output_folder.get())
        path.mkdir(parents=True,exist_ok=True);os.startfile(path)

    def choose_output_folder(self):
        path=filedialog.askdirectory(parent=self,title='选择灯效成品保存目录')
        if path:self.output_folder.set(path)


def main():
    import argparse
    parser=argparse.ArgumentParser(description='WOT 灯效制作器')
    parser.add_argument('project',nargs='?',help='可将 .wotlights 文件拖到启动器打开')
    parser.add_argument('--source', help='从工作台交接的涂装包')
    args=parser.parse_args()
    app=LightMaker()
    if args.source:
        app.source.set(args.source)
        work=app.work_dir()
        app.after(100,lambda:app.job(lambda:engine.scan(args.source,work,app.log,allow_body=True),app.set_project))
    if args.project:
        app.source.set(args.project)
        work=app.work_dir()
        app.after(100,lambda:app.job(lambda:engine.load_project(args.project,work,app.log),app.set_project))
    app.mainloop()


if __name__=='__main__':main()
