"""Colour palette editor. Changes stay local until the user applies them."""
import re
import tkinter as tk
from tkinter import colorchooser, ttk
from .ui_theme import prepare_dialog,register_widget

SWATCHES = ('#FF3030','#FF6B35','#FF9500','#FFD020','#FFFF66','#A8FF00','#30FF80','#00E5A8',
            '#00FFD5','#00D9FF','#36A3FF','#3080FF','#0838FF','#5856FF','#9933FF','#D040FF',
            '#FF00CC','#FF1A75','#FF6FAE','#FFB8DE','#FFE0B2','#FFF5CC','#C9FFD5','#B8FFF4',
            '#B8E7FF','#66BFFF','#D6C2FF','#EECFFF','#FFFFFF','#D4E0FF','#8895B3','#000000')


def normalize_color(value):
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value.strip()):
        raise ValueError('色值请填写 #RRGGBB，例如 #00D9FF。')
    return value.strip().upper()


def parse_colors(value):
    colors=[normalize_color(c) for c in value.replace('，',',').split(',') if c.strip()]
    if len(colors)>12:raise ValueError('颜色最多保留 12 种。')
    return colors


class PaletteDialog(tk.Toplevel):
    def __init__(self,parent,value,on_apply):
        colors=parse_colors(value)
        super().__init__(parent)
        prepare_dialog(self,'灯光调色盘');self.transient(parent);self.resizable(False,False)
        self.colors=colors;self.selected=0 if colors else None;self.on_apply=on_apply
        self.hex_value=tk.StringVar(value=colors[0] if colors else '#00D9FF')
        self.note=tk.StringVar(value='点击色块替换选中色；点“追加颜色”增加下一种颜色。')
        panel=ttk.Frame(self,padding=20);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='搭配你的灯光颜色',style='Section.TLabel').pack(anchor='w')
        ttk.Label(panel,text='当前颜色顺序 · 最多 12 色，按从左到右循环').pack(anchor='w',pady=(12,6))
        self.strip=tk.Frame(panel,background='#f5f5f7');self.strip.pack(fill='x')
        register_widget(self.strip,'surface')
        row=ttk.Frame(panel);row.pack(fill='x',pady=10)
        for text,action in [('追加颜色',self.append_color),('删除选中',self.delete_color),
                            ('左移',lambda:self.move(-1)),('右移',lambda:self.move(1))]:
            ttk.Button(row,text=text,command=action).pack(side='left',padx=(0,6))
        ttk.Label(panel,text='快捷色板').pack(anchor='w',pady=(4,6))
        grid=tk.Frame(panel,background='#f5f5f7');grid.pack(fill='x')
        register_widget(grid,'surface')
        for i,color in enumerate(SWATCHES):
            b=tk.Button(grid,background=color,activebackground=color,width=6,height=2,
                        relief='flat',borderwidth=1,command=lambda c=color:self.set_color(c))
            b.grid(row=i//8,column=i%8,padx=3,pady=3)
        custom=ttk.Frame(panel);custom.pack(fill='x',pady=(12,6))
        ttk.Label(custom,text='自定义色值').pack(side='left')
        self.hex_entry=ttk.Entry(custom,textvariable=self.hex_value,width=12)
        self.hex_entry.pack(side='left',padx=8);self.hex_entry.bind('<Return>',lambda e:self.use_hex())
        ttk.Button(custom,text='使用色值',command=self.use_hex).pack(side='left')
        ttk.Button(custom,text='更多颜色…',command=self.choose_custom).pack(side='left',padx=8)
        ttk.Label(panel,textvariable=self.note,wraplength=520).pack(anchor='w',pady=(4,12))
        footer=ttk.Frame(panel);footer.pack(fill='x')
        ttk.Button(footer,text='应用颜色',command=self.apply,style='Accent.TButton').pack(side='right')
        ttk.Button(footer,text='取消',command=self.destroy).pack(side='right',padx=8)
        self.bind('<Escape>',lambda e:self.destroy());self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.redraw();self.grab_set()
        self.update_idletasks()
        x=parent.winfo_rootx()+max(0,(parent.winfo_width()-self.winfo_reqwidth())//2)
        y=parent.winfo_rooty()+max(0,(parent.winfo_height()-self.winfo_reqheight())//2)
        x=max(0,min(x,self.winfo_screenwidth()-self.winfo_reqwidth()))
        y=max(0,min(y,self.winfo_screenheight()-self.winfo_reqheight()))
        self.geometry('+%d+%d'%(x,y))

    def redraw(self):
        for child in self.strip.winfo_children():child.destroy()
        for i,color in enumerate(self.colors):
            # A numbered chip makes selection and sequence order explicit.
            rgb=[int(color[j:j+2],16) for j in (1,3,5)]
            foreground='#111111' if sum(c*w for c,w in zip(rgb,(.2126,.7152,.0722)))>145 else '#FFFFFF'
            chip=tk.Button(self.strip,text=str(i+1),background=color,foreground=foreground,
                           activebackground=color,activeforeground=foreground,width=3,height=2,
                           relief='sunken' if i==self.selected else 'flat',borderwidth=3,
                           command=lambda index=i:self.select(index))
            chip.pack(side='left',padx=2)
        if not self.colors:ttk.Label(self.strip,text='还没有颜色，请点击快捷色块添加。').pack(anchor='w')

    def select(self,index):
        self.selected=index;self.hex_value.set(self.colors[index]);self.redraw()

    def set_color(self,color):
        try:color=normalize_color(color)
        except ValueError as error:self.note.set(str(error));return
        if self.selected is None:
            self.colors.append(color);self.selected=len(self.colors)-1
        else:self.colors[self.selected]=color
        self.hex_value.set(color);self.note.set('已更新第 %d 色；确认后点击“应用颜色”。'%(self.selected+1));self.redraw()

    def use_hex(self):self.set_color(self.hex_value.get())

    def append_color(self):
        if len(self.colors)>=12:self.note.set('最多 12 种颜色，可先删除一种再追加。');return
        try:color=normalize_color(self.hex_value.get())
        except ValueError as error:self.note.set(str(error));return
        self.colors.append(color);self.select(len(self.colors)-1)
        self.note.set('已追加第 %d 色，点击快捷色块选择它的颜色。'%len(self.colors))

    def delete_color(self):
        if self.selected is None:return
        self.colors.pop(self.selected)
        self.selected=min(self.selected,len(self.colors)-1) if self.colors else None
        if self.selected is not None:self.hex_value.set(self.colors[self.selected])
        self.redraw()

    def move(self,delta):
        if self.selected is None:return
        index=self.selected+delta
        if 0<=index<len(self.colors):
            self.colors[self.selected],self.colors[index]=self.colors[index],self.colors[self.selected]
            self.selected=index;self.redraw()

    def choose_custom(self):
        try:initial=normalize_color(self.hex_value.get())
        except ValueError:initial='#00D9FF'
        _,color=colorchooser.askcolor(color=initial,parent=self,title='选择灯光颜色')
        if color:self.set_color(color)

    def apply(self):
        if not self.colors:self.note.set('请至少添加一种颜色。');return
        self.on_apply(', '.join(self.colors));self.destroy()
