"""Small independent, read-only preparation UI for the pending-test game MOD."""
import queue,threading,tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
from client_catalog import ClientCatalog
from filter_builder import vehicle_list,scan_overrides,installed_inputs,build


class App(ttk.Frame):
    def __init__(self,root):
        super().__init__(root,padding=16);self.pack(fill='both',expand=True)
        self.root=root;root.title('本地涂装屏蔽 1.0 · 待实测');root.geometry('1100x780');root.minsize(900,680)
        self.events=queue.Queue();self.catalog=None;self.vehicles=[];self.selected=set();self.inspection={};self.busy=False
        self.client=tk.StringVar();self.output=tk.StringVar(value=str(Path(__file__).resolve().parent/'输出'))
        self.search=tk.StringVar();self.status=tk.StringVar(value='选择实际使用的 Wargaming 客户端，然后扫描涂装或勾选车型。')
        self.count=tk.StringVar(value='已选 0 款');self.controls=[]
        ttk.Label(self,text='本地涂装屏蔽',font=('Microsoft YaHei UI',19,'bold')).pack(anchor='w')
        ttk.Label(self,text='敌车／队友读取独立原版资源，保留自己的涂装。只生成文件，由你决定何时安装。').pack(anchor='w',pady=(4,12))
        self._path_row('游戏目录',self.client,self.choose_client,'选择客户端')
        self._path_row('输出目录',self.output,self.choose_output,'选择输出目录')
        bar=ttk.Frame(self);bar.pack(fill='x',pady=(8,8))
        for label,command in [('读取车型',self.load_client),('扫描已安装涂装',self.scan_installed),('添加涂装包',self.add_packages),('清空选择',self.clear_selection)]:
            b=ttk.Button(bar,text=label,command=command);b.pack(side='left',padx=(0,8));self.controls.append(b)
        ttk.Label(bar,textvariable=self.count).pack(side='right')
        # Reserve results/actions before the expandable table, including at minimum size.
        bottom=ttk.Frame(self);bottom.pack(side='bottom',fill='x',pady=(12,0))
        ttk.Label(bottom,text='待实测：尚未获得官方审核；不能保证反作弊零误报。',foreground='#855717').pack(anchor='w')
        ttk.Label(bottom,text='游戏内开关需 ModsSettings API ＋ ModsList API；设置在车辆下次正常加载时生效。').pack(anchor='w',pady=(2,6))
        b=ttk.Button(bottom,text='生成待实测包',command=self.generate);b.pack(side='right',padx=(10,0));self.controls.append(b)
        ttk.Label(bottom,textvariable=self.status,wraplength=610,justify='left').pack(side='left',fill='x',expand=True)
        notice=ttk.LabelFrame(self,text='本版范围',padding=8);notice.pack(fill='x',pady=(0,8))
        ttk.Label(notice,text='支持原版路径下的模型／贴图替换。UML、AE 或其他脚本额外挂载的模型／光效不保证屏蔽；\n扫描只列出可保护的车型，不运行包内脚本。不会修改旧涂装、碰撞、点亮、输入或可见性。',justify='left').pack(anchor='w')
        row=ttk.Frame(self);row.pack(fill='x',pady=(0,6));ttk.Label(row,text='搜索车型').pack(side='left')
        entry=ttk.Entry(row,textvariable=self.search);entry.pack(side='left',fill='x',expand=True,padx=(10,0));entry.bind('<KeyRelease>',lambda e:self.render())
        table=ttk.Frame(self);table.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(table,columns=('check','name','source'),show='headings',selectmode='browse')
        for name,text,width in [('check','勾选',64),('name','客户端车型',330),('source','识别到的本地覆盖',480)]:
            self.tree.heading(name,text=text);self.tree.column(name,width=width,minwidth=50,stretch=name!='check')
        scroll=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.tree.pack(side='left',fill='both',expand=True)
        self.tree.bind('<Double-1>',self.toggle);self.tree.bind('<space>',self.toggle)
        ttk.Label(self,text='双击一行或按空格勾选；扫描命中的车型会自动勾选。').pack(anchor='w',pady=(4,0))
        self.root.protocol('WM_DELETE_WINDOW',self.close);self._poll_job=self.root.after(100,self.poll)

    def _path_row(self,text,var,command,button):
        row=ttk.Frame(self);row.pack(fill='x',pady=3);ttk.Label(row,text=text,width=10).pack(side='left')
        e=ttk.Entry(row,textvariable=var);e.pack(side='left',fill='x',expand=True,padx=(0,8));self.controls.append(e)
        b=ttk.Button(row,text=button,command=command);b.pack(side='right');self.controls.append(b)

    def choose_client(self):
        value=filedialog.askdirectory(title='选择包含 paths.xml 和 version.xml 的实际游戏目录')
        if value:self.client.set(value);self.load_client()

    def choose_output(self):
        value=filedialog.askdirectory(title='选择游戏目录以外的输出目录')
        if value:self.output.set(value)

    def run(self,worker,finish):
        if self.busy:return
        self.busy=True
        for b in self.controls:b.configure(state='disabled')
        def background():
            try:self.events.put(('done',finish,worker()))
            except Exception as error:self.events.put(('error',str(error)))
        threading.Thread(target=background,daemon=True).start()

    def poll(self):
        try:
            while True:
                event=self.events.get_nowait()
                if event[0]=='progress':self.status.set(event[1]);continue
                self.busy=False
                for b in self.controls:b.configure(state='normal')
                if event[0]=='error':self.status.set('未完成：'+event[1]);messagebox.showerror('未生成可用版本',event[1])
                else:event[1](event[2])
        except queue.Empty:pass
        self._poll_job=self.root.after(100,self.poll)

    def destroy(self):
        job=getattr(self,'_poll_job',None)
        if job:
            try:self.root.after_cancel(job)
            except tk.TclError:pass
        super().destroy()

    def load_client(self):
        selected=self.client.get().strip()
        if not selected:messagebox.showinfo('选择客户端','请先选择实际使用的游戏目录。');return
        self.status.set('读取客户端原版资源目录…')
        self.run(lambda:ClientCatalog(selected).scan(),self.loaded)

    def loaded(self,catalog):
        if self.catalog:self.catalog.close()
        self.catalog=catalog;self.client.set(str(catalog.root));self.vehicles=vehicle_list(catalog);self.selected.clear();self.inspection={}
        self.status.set(catalog.realm+' · '+catalog.version+'；读取 '+str(len(self.vehicles))+' 款车型。');self.render()

    def require_catalog(self):
        if self.catalog is None or Path(self.client.get()).resolve()!=self.catalog.root:
            messagebox.showinfo('先读取车型','请先读取当前所选客户端的车型。');return False
        return True

    def scan_installed(self):
        if not self.require_catalog():return
        self.status.set('只读扫描已安装涂装，不运行脚本…')
        self.run(lambda:scan_overrides(self.catalog,installed_inputs(self.catalog.root)),self.scanned)

    def add_packages(self):
        if not self.require_catalog():return
        values=filedialog.askopenfilenames(title='选择待识别的涂装包（不修改原包）',filetypes=[('WOT 涂装包','*.wotmod'),('ZIP 包','*.zip')])
        if values:self.run(lambda:scan_overrides(self.catalog,values),self.scanned)

    def scanned(self,result):
        self.inspection=result;self.selected.update(result['vehicles']);self.render()
        self.status.set('命中 '+str(len(result['vehicles']))+' 款车型。'+(' 有脚本或自有模型，仅保护原版路径。'if result['warnings']else''))
        if result['warnings']:messagebox.showinfo('扫描范围提示','\n'.join(result['warnings'][:8]))

    def render(self):
        self.tree.delete(*self.tree.get_children());query=self.search.get().strip().casefold()
        hits=self.inspection.get('vehicles',{})
        for row in self.vehicles:
            if query and query not in(row['key']+' '+row['label']).casefold():continue
            self.tree.insert('', 'end', iid=row['key'],values=('☑'if row['key']in self.selected else'☐',row['label'],
                '；'.join(Path(x).name for x in hits.get(row['key'],[]))))
        self.count.set('已选 '+str(len(self.selected))+' 款')

    def toggle(self,event=None):
        if self.busy:return 'break'
        row=self.tree.identify_row(event.y)if event is not None and getattr(event,'y',0)>0 else self.tree.focus()
        if not row:return 'break'
        if row in self.selected:self.selected.remove(row)
        else:self.selected.add(row)
        self.render();self.tree.focus(row);self.tree.selection_set(row);return 'break'

    def clear_selection(self):self.selected.clear();self.render()

    def generate(self):
        if not self.require_catalog():return
        if not self.selected:messagebox.showinfo('选择车型','请扫描涂装或勾选至少一款车型。');return
        selected=tuple(self.selected);output=self.output.get().strip()
        if not output:messagebox.showinfo('选择输出目录','请选择游戏目录以外的输出目录。');return
        self.run(lambda:build(self.catalog,selected,output,self.inspection,
            progress=lambda s:self.events.put(('progress',s))),self.generated)

    def generated(self,result):
        target,record=result;self.status.set('已生成待实测包：'+str(target))
        messagebox.showinfo('待实测包已生成','位置：'+str(target)+'\n\n游戏内效果与兼容性尚未验证。先查看同目录的使用说明和验证记录。')

    def close(self):
        if self.busy:messagebox.showinfo('正在处理','请等待本次读取或生成结束后再关闭。');return
        if self.catalog:self.catalog.close()
        self.root.destroy()


def main():
    root=tk.Tk();App(root);root.mainloop()


if __name__=='__main__':main()
