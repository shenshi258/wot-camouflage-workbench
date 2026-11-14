"""Small independent UI for own-vehicle skin conversion; no workbench required."""
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
from batch_convert import APP_NAME,analyse_many,convert_many
from client_catalog import ClientCatalog

ROOT=Path(__file__).resolve().parent


class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title(APP_NAME);self.geometry('1040x740');self.minsize(800,600)
        self.option_add('*Font',('Microsoft YaHei UI',10))
        style=ttk.Style(self);style.theme_use('clam')
        style.configure('.',font=('Microsoft YaHei UI',10),background='#f5f7fb',foreground='#1f2937')
        style.configure('TButton',padding=(10,6));style.configure('Accent.TButton',background='#2469c7',foreground='white')
        style.map('Accent.TButton',background=[('active','#1d5eb8'),('disabled','#d8e2ef')],foreground=[('disabled','#6c7c8e')])
        style.configure('Treeview',rowheight=28,fieldbackground='white',background='white')
        self.configure(bg='#f5f7fb')
        self.inputs=[];self.results=[];self.events=queue.Queue();self.busy=False;self.cancel=threading.Event();self.closing=False
        self.client=tk.StringVar();self.output=tk.StringVar(value=str(ROOT/'转换结果'))
        self.baseline=tk.BooleanVar(value=False);self.client_info=tk.StringVar(value='请选择实际使用的客户端；不会自动安装模组。')
        self.status=tk.StringVar(value='可批量添加普通涂装、UML 配置包和已适配的脚本包。')
        outer=ttk.Frame(self,padding=16);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text=APP_NAME,font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w')
        ttk.Label(outer,text='固定转换为仅自己的车辆 · 原包保留 · 结果另存 · 游戏效果待实测').pack(anchor='w',pady=(4,12))
        files=ttk.Frame(outer);files.pack(fill='x')
        self.controls=[]
        for label,callback in [('添加涂装包',self.add),('添加文件夹',self.add_folder),('移除所选',self.remove),('清空',self.clear)]:
            button=ttk.Button(files,text=label,command=callback);button.pack(side='left',padx=(0,6));self.controls.append(button)
        listing=ttk.Frame(outer);listing.pack(fill='both',expand=True,pady=(9,10))
        self.table=ttk.Treeview(listing,columns=('name','type','vehicles','status'),show='headings',height=8)
        for name,title,width in [('name','输入涂装',290),('type','包型',150),('vehicles','车型',210),('status','处理状态',180)]:
            self.table.heading(name,text=title);self.table.column(name,width=width,minwidth=80,stretch=True)
        scroll=ttk.Scrollbar(listing,orient='vertical',command=self.table.yview);self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.table.bind('<<TreeviewSelect>>',self.show_selected)
        footer=ttk.Frame(outer);footer.pack(side='bottom',fill='x')
        self.path_row(footer,'实际游戏目录',self.client,self.browse_client)
        ttk.Label(footer,textvariable=self.client_info,foreground='#536681').pack(anchor='w',pady=(2,5))
        self.path_row(footer,'结果输出目录',self.output,self.browse_output)
        baseline=ttk.Checkbutton(footer,text='已确认原包在所选客户端正常显示（可选，仅记录为用户确认）',variable=self.baseline)
        baseline.pack(anchor='w',pady=(6,7));self.controls.append(baseline)
        actions=ttk.Frame(footer);actions.pack(fill='x')
        for label,callback,accent in [('检查包型',self.inspect,False),('批量转换为仅本车',self.convert,True),('打开输出目录',self.open_output,False)]:
            button=ttk.Button(actions,text=label,command=callback,style='Accent.TButton'if accent else'TButton')
            button.pack(side='left',padx=(0,7));self.controls.append(button)
        self.stop=ttk.Button(actions,text='停止后续任务',command=self.cancel.set,state='disabled');self.stop.pack(side='right')
        self.progress=ttk.Progressbar(footer,mode='indeterminate');self.progress.pack(fill='x',pady=(9,4))
        ttk.Label(footer,textvariable=self.status,wraplength=750).pack(anchor='w',pady=(0,5))
        self.detail=tk.Text(footer,height=6,wrap='word',relief='flat',bg='white',fg='#334155',padx=8,pady=6,state='disabled')
        self.detail.pack(fill='x')
        # Reserve paths/actions/details first; the file list absorbs resizing.
        listing.pack_forget();listing.pack(fill='both',expand=True,pady=(9,10))
        self._poll=self.after(100,self.poll);self.protocol('WM_DELETE_WINDOW',self.close)

    def path_row(self,parent,label,variable,browse):
        row=ttk.Frame(parent);row.pack(fill='x',pady=3)
        ttk.Label(row,text=label,width=13).pack(side='left')
        entry=ttk.Entry(row,textvariable=variable);entry.pack(side='left',fill='x',expand=True,padx=(0,7));self.controls.append(entry)
        button=ttk.Button(row,text='浏览',command=browse);button.pack(side='left');self.controls.append(button)

    def set_detail(self,text):
        self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('1.0',text);self.detail.configure(state='disabled')

    def add_paths(self,paths):
        if self.busy:return
        existing={str(p).casefold()for p in self.inputs}
        for value in paths:
            path=Path(value).resolve()
            if path.suffix.lower()in('.wotmod','.zip')and str(path).casefold()not in existing:
                self.inputs.append(path);existing.add(str(path).casefold())
        self.results=[];self.refresh_inputs();self.status.set('已添加 %d 个输入文件。'%len(self.inputs))

    def refresh_inputs(self):
        self.table.delete(*self.table.get_children())
        for index,path in enumerate(self.inputs):self.table.insert('','end',iid=str(index),values=(path.name,'待识别','自动识别','等待处理'))

    def add(self):
        self.add_paths(filedialog.askopenfilenames(title='选择涂装包（可多选）',filetypes=[('涂装包','*.wotmod *.zip')]))

    def add_folder(self):
        folder=filedialog.askdirectory(title='添加文件夹中的涂装包')
        if folder:self.add_paths(sorted(p for p in Path(folder).iterdir()if p.is_file()and p.suffix.lower()in('.wotmod','.zip')))

    def remove(self):
        if self.busy:return
        selected={int(i)for i in self.table.selection()}
        remove_paths={Path(self.results[i]['path']).resolve()for i in selected}if self.results else{self.inputs[i]for i in selected}
        self.inputs=[p for p in self.inputs if p not in remove_paths]
        self.results=[];self.refresh_inputs()

    def clear(self):
        if self.busy:return
        self.inputs=[];self.results=[];self.refresh_inputs();self.set_detail('')

    def browse_client(self):
        selected=filedialog.askdirectory(title='选择实际游戏客户端（也可选 mods 子目录）')
        if not selected:return
        try:
            catalog=ClientCatalog(selected);self.client.set(str(catalog.root))
            self.client_info.set('已选：'+catalog.realm+' '+catalog.version);catalog.close()
        except (ValueError,OSError)as error:messagebox.showerror('客户端无法读取',str(error),parent=self)

    def browse_output(self):
        selected=filedialog.askdirectory(title='选择游戏目录以外的输出文件夹')
        if selected:self.output.set(selected)

    def open_output(self):
        folder=Path(self.output.get()).expanduser()
        if folder.is_dir():os.startfile(folder)
        else:messagebox.showinfo('尚无输出','先完成转换，或选择已经存在的输出目录。',parent=self)

    def set_busy(self,value):
        self.busy=value
        for control in self.controls:control.configure(state='disabled'if value else'normal')
        self.stop.configure(state='normal'if value else'disabled')
        if value:self.cancel.clear();self.progress.start(15)
        else:self.progress.stop()

    def inspect(self):self.start_job(False)
    def convert(self):self.start_job(True)

    def start_job(self,convert):
        if self.busy or not self.inputs:return
        client=self.client.get().strip();output=self.output.get().strip();paths=list(self.inputs)
        if convert and(not client or not output):
            messagebox.showerror('信息不完整','请选择实际游戏客户端和输出目录。',parent=self);return
        baseline=self.baseline.get();self.set_busy(True)
        def worker():
            try:
                if convert:
                    results,report=convert_many(paths,client,output,
                        progress=lambda n,total,name:self.events.put(('progress',(n,total,name))),
                        cancel=self.cancel,baseline_confirmed=baseline)
                    self.events.put(('done',(results,str(report))))
                else:self.events.put(('done',(analyse_many(paths),None)))
            except Exception as error:self.events.put(('error',str(error)))
        threading.Thread(target=worker,daemon=True).start()

    def show_results(self,results):
        self.results=results;self.table.delete(*self.table.get_children())
        for index,row in enumerate(results):
            status={'candidate':'已生成（待实测）','error':'未生成／需适配','cancelled':'已停止','analysis_only':'已识别'}.get(row['status'],row['status'])
            self.table.insert('','end',iid=str(index),values=(row.get('name')or Path(row['path']).name,
                row.get('package_type','—'),'、'.join(row.get('vehicles',[])),status))
        if results:self.table.selection_set('0');self.show_selected()

    def show_selected(self,event=None):
        selected=self.table.selection()
        if not selected:return
        index=int(selected[0])
        if not self.results:
            if index<len(self.inputs):self.set_detail(str(self.inputs[index]))
            return
        row=self.results[index];lines=[row.get('name')or row['path']]
        if row.get('error'):lines.append(row['error'])
        if row.get('target'):lines.extend(['待测包：'+row['target'],'原包保留；游戏内整车加载与仅本车效果尚未实测。'])
        record=row.get('record',{})
        if record.get('adapter')=='uml_swapNPC':
            lines.append('保留 UML 动画、物理参数、启用状态和白名单；需要原 UML 加载器。')
            if record['offline_validation'].get('disabled_profiles'):lines.append('注意：原包含关闭的方案，本次未自动开启。')
            missing=record.get('file_validation',{}).get('preexisting_missing_dependencies',[])
            if missing:lines.append('原包有 %d 项缺失依赖，已保留并记录；请先核对原包效果。'%len(missing))
        adapted=record.get('offline_validation',{}).get('adapted_scripts',[])
        if adapted:lines.append('已适配脚本：'+', '.join(item['adapter']for item in adapted))
        if row.get('observations'):lines.extend(row['observations'])
        self.set_detail('\n'.join(lines))

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    n,total,name=value;self.status.set('正在处理 %d：%s'%(n,name))
                elif kind=='error':
                    self.set_busy(False);self.status.set('未完成：'+value);self.set_detail(value)
                    if self.closing:self.destroy();return
                elif kind=='done':
                    results,report=value;self.set_busy(False);self.show_results(results)
                    made=sum(r['status']=='candidate'for r in results)
                    self.status.set(('已生成 %d 个待测包，未生成 %d 个。'%(made,len(results)-made))if report else'检查完成；选择条目查看详情。')
                    if report:self.status.set(self.status.get()+' 批次记录已保存。')
                    if self.closing:self.destroy();return
        except queue.Empty:pass
        self._poll=self.after(100,self.poll)

    def close(self):
        if self.busy:self.closing=True;self.cancel.set();self.status.set('完成当前包后关闭，后续任务已停止。')
        else:self.destroy()

    def destroy(self):
        if getattr(self,'_poll',None):
            try:self.after_cancel(self._poll)
            except tk.TclError:pass
            self._poll=None
        super().destroy()


if __name__=='__main__':App().mainloop()
