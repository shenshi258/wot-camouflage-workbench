"""Themed media-segment import and a local, client-independent animation preview."""
import time
import tkinter as tk
from tkinter import ttk,messagebox
import numpy as np
from PIL import Image,ImageTk
from . import ae_effects as ae,ae_media as media,ae_help
from .light_tooltips import HoverHelp
from .ui_theme import prepare_dialog,register_widget


class MediaImportDialog(tk.Toplevel):
    def __init__(self,parent,info,on_import):
        super().__init__(parent);self.info=info;self.on_import=on_import
        prepare_dialog(self,'导入动画素材');self.geometry('680x480');self.minsize(640,460);self.transient(parent)
        self.hover_help=HoverHelp(self)
        self.parameters={key:tk.StringVar(self,value=format(value,'.9g')) for key,value in media.defaults(info).items()}
        self.alpha_mode=tk.StringVar(self,value=next(iter(media.ALPHA_MODES)))
        self.status=tk.StringVar(self);self.fields={}
        box=ttk.Frame(self,padding=20,style='Backdrop.TFrame');box.pack(fill='both',expand=True)
        footer=ttk.Frame(box);footer.pack(side='bottom',fill='x',pady=(12,0))
        ttk.Button(footer,text='取消',command=self.destroy).pack(side='right')
        self.import_button=ttk.Button(footer,text='导入动画',style='Accent.TButton',command=self.submit);self.import_button.pack(side='right',padx=8)
        self.hover_help.attach(self.import_button,lambda event:ae_help.topic('media_import'))
        ttk.Label(box,text='导入 GIF / 视频动画',style='Section.TLabel').pack(anchor='w')
        ttk.Label(box,text=info['name'][:70]+('…' if len(info['name'])>70 else ''),wraplength=610).pack(anchor='w',pady=(10,4))
        ttk.Label(box,text='%d×%d · %.3f 秒 · 原素材约 %.2f FPS'%(info['width'],info['height'],info['duration'],info['native_fps']),style='Muted.TLabel').pack(anchor='w')
        group=ttk.LabelFrame(box,text='截取片段',padding=12);group.pack(fill='x',pady=14)
        for key,label,topic in [('start','开始时间（秒）','media_start'),('end','结束时间（秒）','media_end'),('fps','导入帧率（FPS）','media_fps')]:
            row=ttk.Frame(group);row.pack(fill='x',pady=4);ttk.Label(row,text=label,width=19).pack(side='left')
            field=ttk.Entry(row,textvariable=self.parameters[key],width=18);field.pack(side='left');self.fields[key]=field
            self.hover_help.attach(field,lambda event,k=topic:ae_help.topic(k))
        mode=ttk.Frame(box);mode.pack(fill='x');ttk.Label(mode,text='背景处理',width=19).pack(side='left')
        self.mode_combo=ttk.Combobox(mode,textvariable=self.alpha_mode,values=list(media.ALPHA_MODES),state='readonly',width=27);self.mode_combo.pack(side='left')
        self.hover_help.attach(self.mode_combo,lambda event:ae_help.topic('media_alpha'))
        ttk.Label(box,text='GIF 保留透明；普通视频保留完整画面。黑底光效可选“黑底转透明”。仅导入画面，不含音轨。',wraplength=610,style='Muted.TLabel').pack(anchor='w',pady=(12,5))
        ttk.Label(box,textvariable=self.status,wraplength=610).pack(anchor='w',pady=(6,0))
        for var in list(self.parameters.values())+[self.alpha_mode]:var.trace_add('write',self.refresh)
        self.refresh();self.grab_set()

    def selection(self):
        selected=media.plan(self.info,**{k:v.get() for k,v in self.parameters.items()})
        return dict(start=selected['start'],end=selected['end'],fps=selected['fps'],alpha_mode=media.ALPHA_MODES[self.alpha_mode.get()])

    def refresh(self,*args):
        try:
            selected=media.plan(self.info,**{k:v.get() for k,v in self.parameters.items()})
            self.status.set('将导入 %d 帧 · 播放 %.3f 秒。最多 128 帧；作为当前动画素材导入，车辆与摆放参数保留。'%(selected['frames'],selected['seconds']))
            self.import_button.state(['!disabled'])
        except ValueError as error:self.status.set(str(error));self.import_button.state(['disabled'])

    def submit(self):
        try:options=self.selection()
        except ValueError as error:return messagebox.showerror('导入设置',str(error),parent=self)
        self.destroy();self.on_import(options)


class ClipPreview(tk.Toplevel):
    def __init__(self,parent,clip,values):
        super().__init__(parent);prepare_dialog(self,'动画素材预览');self.geometry('540x380');self.minsize(480,340);self.transient(parent)
        self.clip=clip;self.values=ae.config(values)
        self.hover_help=HoverHelp(self)
        with Image.open(clip['atlas']) as image:self.atlas=ae.appearance_rgba(image,self.values)
        self.started=time.monotonic();self.paused=None;self.last_frame=-1;self.timer=None;self.photo=None
        box=ttk.Frame(self,padding=15,style='Backdrop.TFrame');box.pack(fill='both',expand=True)
        # 先为操作栏留位，小窗口也能暂停、重播和关闭。
        actions=ttk.Frame(box);actions.pack(side='bottom',fill='x',pady=(10,0))
        self.play_button=ttk.Button(actions,text='暂停',command=self.toggle);self.play_button.pack(side='left')
        self.restart_button=ttk.Button(actions,text='从头播放',command=self.restart);self.restart_button.pack(side='left',padx=8)
        self.close_button=ttk.Button(actions,text='关闭',command=self.destroy);self.close_button.pack(side='right')
        for button,key in [(self.play_button,'media_play'),(self.restart_button,'media_restart'),(self.close_button,'media_close')]:self.hover_help.attach(button,lambda event,k=key:ae_help.topic(k))
        self.canvas=tk.Canvas(box,width=480,height=250,highlightthickness=0,bg='#152033');self.canvas.pack(fill='both',expand=True);register_widget(self.canvas,'surface')
        self.canvas.bind('<Configure>',lambda event:self.draw_frame(force=True))
        self.label=tk.StringVar(self);ttk.Label(box,textvariable=self.label).pack(anchor='w',pady=5)
        ttk.Label(box,text='检查素材播放与透明边缘；车身位置请打开三维预览。此处不是游戏内曝光。',wraplength=490,style='Muted.TLabel').pack(anchor='w')
        self.bind('<Destroy>',self.cleanup,add='+');self.tick()

    def tick(self):
        self.draw_frame()
        self.timer=self.after(max(16,round(1000/self.values['fps'])),self.tick)

    def draw_frame(self,force=False):
        # 用经过时间选帧，避免 Tk 定时回调延迟让动画越播越慢。
        elapsed=self.paused if self.paused is not None else time.monotonic()-self.started
        frame=int(elapsed*self.values['fps'])%self.clip['frames']
        if force or frame!=self.last_frame:
            self.last_frame=frame;w,h=self.atlas.size;u,v,r,b=self.clip['rects'][frame]
            tile=self.atlas.crop((round(u*w-.5),round(v*h-.5),round(r*w+.5),round(b*h+.5)))
            tile.thumbnail((max(1,min(460,self.canvas.winfo_width()-16)),max(1,min(230,self.canvas.winfo_height()-16))),Image.Resampling.LANCZOS);rgba=np.asarray(tile,dtype=float)/255
            yy,xx=np.indices((tile.height,tile.width));shade=np.where((xx//12+yy//12)%2,.09,.14)
            bg=np.stack((shade*.8,shade,shade*1.3),axis=2)
            alpha=rgba[:,:,3:];colour=rgba[:,:,:3]*self.values['brightness']*alpha
            colour+=bg if self.values['blend']=='add' else bg*(1-alpha)
            self.photo=ImageTk.PhotoImage(Image.fromarray(np.uint8(np.clip(colour,0,1)*255+.5)),master=self)
            self.canvas.delete('all');self.canvas.create_image(self.canvas.winfo_width()/2,self.canvas.winfo_height()/2,image=self.photo)
            self.label.set('%d / %d 帧 · %g FPS · %.3f 秒循环'%(frame+1,self.clip['frames'],self.values['fps'],self.clip['frames']/self.values['fps']))

    def toggle(self):
        if self.paused is None:self.paused=time.monotonic()-self.started;self.play_button.configure(text='继续')
        else:self.started=time.monotonic()-self.paused;self.paused=None;self.play_button.configure(text='暂停')

    def restart(self):self.started=time.monotonic();self.paused=None;self.last_frame=-1;self.play_button.configure(text='暂停')

    def cleanup(self,event):
        if event.widget is self and self.timer:
            self.after_cancel(self.timer);self.timer=None
