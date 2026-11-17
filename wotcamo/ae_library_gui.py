"""Persistent picture/GIF picker shared with the workbench's material library."""
import bisect,io,queue,threading,time
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk
from .asset_library import Library
from .ui_theme import prepare_dialog,register_widget


class AssetLibraryDialog(tk.Toplevel):
    def __init__(self,parent,on_use,store=None):
        super().__init__(parent);prepare_dialog(self,'图片 / GIF 素材库');self.transient(parent)
        width=max(720,min(940,self.winfo_screenwidth()-60));height=max(470,min(620,self.winfo_screenheight()-110))
        self.geometry('%dx%d'%(width,height));self.minsize(700,460)
        self.on_use=on_use;self.store=store if store is not None else Library()
        self.items=[];self.selected=None;self.busy=False;self.closed=False;self.events=queue.Queue();self.cancel=threading.Event()
        self.photos={};self.preview_photo=None;self.preview_image=None;self.preview_started=0.;self.preview_delays=[];self.preview_ends=[];self.preview_index=-1
        self.preview_timer=None;self.poll_timer=None
        self.search=tk.StringVar(self);self.category=tk.StringVar(self,value='未分类')
        self.status=tk.StringVar(self,value='图片与 GIF 保存在程序“素材库/图片元素”，下次打开仍可复用。')
        self.chosen_name=tk.StringVar(self,value='选择素材后预览');self.chosen_info=tk.StringVar(self);self.clock=tk.StringVar(self)
        self.interface();self.search.trace_add('write',lambda *args:self.render())
        self.bind('<Destroy>',self.cleanup,add='+');self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.refresh();self.poll_timer=self.after(100,self.poll)

    def interface(self):
        box=ttk.Frame(self,padding=14,style='Backdrop.TFrame');box.pack(fill='both',expand=True)
        ttk.Label(box,text='图片 / GIF 素材库',style='Section.TLabel').pack(anchor='w')
        ttk.Label(box,text='保存自己的素材，选择后载入 AE；GIF 保留动画，图片可继续添加动画节点。',style='Muted.TLabel',wraplength=740).pack(anchor='w',pady=(5,10))
        footer=ttk.Frame(box);footer.pack(side='bottom',fill='x',pady=(10,0))
        self.use_button=ttk.Button(footer,text='使用所选素材',command=self.use_selected,style='Accent.TButton');self.use_button.pack(side='right')
        ttk.Button(footer,text='关闭',command=self.destroy).pack(side='right',padx=8)
        ttk.Label(footer,textvariable=self.status,wraplength=420,style='Muted.TLabel').pack(side='left',fill='x',expand=True)
        toolbar=ttk.Frame(box);toolbar.pack(fill='x',pady=(0,10))
        self.import_button=ttk.Button(toolbar,text='导入图片 / GIF…',command=self.choose_files);self.import_button.pack(side='left')
        self.refresh_button=ttk.Button(toolbar,text='刷新',command=self.refresh);self.refresh_button.pack(side='left',padx=7)
        ttk.Label(toolbar,text='导入分类').pack(side='left',padx=(5,5));self.category_entry=ttk.Entry(toolbar,textvariable=self.category,width=13);self.category_entry.pack(side='left')
        search=ttk.Frame(box);search.pack(fill='x',pady=(0,8));ttk.Label(search,text='搜索名称 / 分类').pack(side='left',padx=(0,8))
        self.search_entry=ttk.Entry(search,textvariable=self.search);self.search_entry.pack(side='left',fill='x',expand=True)
        body=ttk.Frame(box);body.pack(fill='both',expand=True);body.columnconfigure(0,weight=1);body.columnconfigure(1,weight=0,minsize=230);body.rowconfigure(0,weight=1)
        listing=ttk.Frame(body);listing.grid(row=0,column=0,sticky='nsew',padx=(0,12));listing.rowconfigure(0,weight=1);listing.columnconfigure(0,weight=1)
        style=ttk.Style(self);style.configure('AEAssets.Treeview',rowheight=62)
        self.tree=ttk.Treeview(listing,show='tree headings',columns=('kind','category'),selectmode='browse',style='AEAssets.Treeview',height=5)
        self.tree.heading('#0',text='素材缩略图与名称');self.tree.heading('kind',text='格式');self.tree.heading('category',text='分类')
        self.tree.column('#0',width=220,minwidth=125,stretch=True);self.tree.column('kind',width=48,minwidth=45,stretch=False);self.tree.column('category',width=82,minwidth=55,stretch=False)
        self.tree.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(listing,orient='vertical',command=self.tree.yview);scroll.grid(row=0,column=1,sticky='ns');self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>',self.selection_changed);self.tree.bind('<Double-1>',lambda event:self.use_selected())
        right=ttk.Frame(body);right.grid(row=0,column=1,sticky='nsew');right.columnconfigure(0,weight=1);right.rowconfigure(2,weight=1)
        ttk.Label(right,textvariable=self.chosen_name,wraplength=230,style='Section.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(right,textvariable=self.chosen_info,wraplength=230,style='Muted.TLabel').grid(row=1,column=0,sticky='w',pady=(5,8))
        self.canvas=tk.Canvas(right,width=230,height=190,highlightthickness=0);register_widget(self.canvas,'surface');self.canvas.grid(row=2,column=0,sticky='nsew')
        self.canvas.bind('<Configure>',lambda event:self.draw_preview(force=True))
        ttk.Label(right,textvariable=self.clock,wraplength=230,style='Muted.TLabel').grid(row=3,column=0,sticky='w',pady=(6,5))
        ttk.Label(right,text='单项最多 8 MB。可在主窗口的素材库中修改名称、分类或移出素材。',wraplength=230,style='Muted.TLabel').grid(row=4,column=0,sticky='w')

    def refresh(self,select=None):
        if self.busy:return
        try:
            result=self.store.list();self.items=result['items'];self.render(select)
            self.status.set('共 %d 项素材%s。'%(len(self.items),'，%d 项记录无法读取'%result['issues'] if result['issues'] else ''))
        except (OSError,ValueError) as error:self.status.set(str(error))

    def render(self,select=None):
        if self.closed:return
        key=select or (self.selected or {}).get('id');query=self.search.get().strip().casefold()
        self.tree.delete(*self.tree.get_children());self.photos={}
        for item in self.items:
            if query and query not in (item['name']+' '+item['category']).casefold():continue
            photo=None
            try:
                data,_=self.store.image(item['id'],thumbnail=True)
                with Image.open(io.BytesIO(data)) as image:
                    image=image.convert('RGBA');image.thumbnail((54,54),Image.Resampling.LANCZOS);photo=ImageTk.PhotoImage(image,master=self)
                self.photos[item['id']]=photo
            except (OSError,ValueError):pass
            options=dict(iid=item['id'],text=item['name'],values=(item['format'],item['category']))
            if photo is not None:options['image']=photo
            self.tree.insert('','end',**options)
        if key and self.tree.exists(key):self.tree.selection_set(key);self.tree.see(key)
        else:self.select_item(None)
        self.update_buttons()

    def selection_changed(self,event=None):
        keys=self.tree.selection();key=keys[0] if keys else None
        self.select_item(next((item for item in self.items if item['id']==key),None))

    def select_item(self,item):
        self.stop_preview();self.selected=item;self.canvas.delete('all')
        if not item:
            self.chosen_name.set('选择素材后预览');self.chosen_info.set('');self.clock.set('');self.update_buttons();return
        self.chosen_name.set(item['name']);self.chosen_info.set('%s · %d×%d\n%s'%(item['format'],item['width'],item['height'],item['category']))
        try:
            record=self.store.record(item['id']);raw,_=self.store.image(item['id']);self.preview_image=Image.open(io.BytesIO(raw))
            self.preview_delays=record.get('durations_ms',[]);total=0.;self.preview_ends=[]
            for delay in self.preview_delays:total+=delay/1000;self.preview_ends.append(total)
            self.preview_started=time.monotonic();self.preview_index=-1;self.tick_preview()
        except (OSError,ValueError) as error:self.status.set('预览未能读取：'+str(error));self.stop_preview()
        self.update_buttons()

    def stop_preview(self):
        if self.preview_timer is not None:
            self.after_cancel(self.preview_timer);self.preview_timer=None
        if self.preview_image is not None:self.preview_image.close();self.preview_image=None
        self.preview_photo=None;self.preview_delays=[];self.preview_ends=[];self.preview_index=-1

    def draw_preview(self,force=False):
        if self.closed or self.preview_image is None:return
        elapsed=time.monotonic()-self.preview_started
        index=min(len(self.preview_delays)-1,bisect.bisect_right(self.preview_ends,elapsed%self.preview_ends[-1])) if self.preview_ends else 0
        if not force and index==self.preview_index:return
        self.preview_index=index
        try:
            # Pillow's sequential seek keeps GIF disposal/compositing semantics;
            # elapsed time chooses the frame so delayed Tk callbacks never drift.
            self.preview_image.seek(index);image=self.preview_image.convert('RGBA')
            image.thumbnail((max(1,self.canvas.winfo_width()-12),max(1,self.canvas.winfo_height()-12)),Image.Resampling.LANCZOS)
            self.preview_photo=ImageTk.PhotoImage(image,master=self);self.canvas.delete('all')
            self.canvas.create_image(self.canvas.winfo_width()/2,self.canvas.winfo_height()/2,image=self.preview_photo)
            self.clock.set('%d / %d 帧 · %.2f 秒循环'%(index+1,len(self.preview_delays),self.preview_ends[-1]) if self.preview_ends else '静态图片 · 可添加动画节点')
        except (OSError,ValueError,EOFError) as error:self.status.set('GIF 预览中断：'+str(error));self.stop_preview()

    def tick_preview(self):
        self.preview_timer=None;self.draw_preview()
        if not self.closed and self.preview_image is not None and len(self.preview_delays)>1:
            elapsed=(time.monotonic()-self.preview_started)%self.preview_ends[-1]
            index=min(len(self.preview_ends)-1,bisect.bisect_right(self.preview_ends,elapsed))
            delay=max(25,min(100,round((self.preview_ends[index]-elapsed)*1000)))
            self.preview_timer=self.after(delay,self.tick_preview)

    def choose_files(self):
        if self.busy:return
        paths=filedialog.askopenfilenames(parent=self,title='导入自己的图片 / GIF',filetypes=[('图片 / GIF','*.png *.jpg *.jpeg *.webp *.gif')])
        if paths:self.import_files(paths)

    def import_files(self,paths):
        if self.busy or not paths:return
        if len(paths)>128:return messagebox.showerror('导入数量','每批最多 128 项，请分批导入。',parent=self)
        category=self.category.get();self.busy=True;self.cancel.clear();self.update_buttons()
        def work():
            added=0;duplicates=0;errors=[];last=None
            for index,path in enumerate(paths):
                if self.cancel.is_set():break
                self.events.put(('progress','正在导入 %d / %d…'%(index+1,len(paths))))
                try:
                    result=self.store.import_file(path,category);last=result['item']['id']
                    if result['duplicate']:duplicates+=1
                    else:added+=1
                except (OSError,ValueError) as error:errors.append(str(error))
            self.events.put(('done',(added,duplicates,errors,last)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        if self.closed:return
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':self.status.set(value)
                else:
                    self.busy=False;added,duplicates,errors,last=value;self.search.set('');self.refresh(last)
                    self.status.set('导入完成：新增 %d，重复 %d，失败 %d%s'%(added,duplicates,len(errors),'；'+errors[0] if errors else ''));self.update_buttons()
        except queue.Empty:pass
        self.poll_timer=self.after(100,self.poll)

    def update_buttons(self):
        for button in (self.import_button,self.refresh_button):button.state(['disabled'] if self.busy else ['!disabled'])
        self.category_entry.state(['disabled'] if self.busy else ['!disabled'])
        self.use_button.state(['disabled'] if self.busy or not self.selected else ['!disabled'])

    def use_selected(self):
        if self.busy or not self.selected:return
        try:
            item=self.store.record(self.selected['id'])
            if self.on_use(item) is not False:self.destroy()
        except (OSError,ValueError) as error:messagebox.showerror('无法使用素材',str(error),parent=self)

    def cleanup(self,event):
        if event.widget is not self or self.closed:return
        self.closed=True;self.cancel.set();self.stop_preview()
        if self.poll_timer is not None:self.after_cancel(self.poll_timer);self.poll_timer=None
