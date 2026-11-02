"""Delayed, non-focusing hover help for native Tk/ttk controls and choices."""
import tkinter as tk
import weakref
from .ui_theme import CARD,INK,MUTED,BORDER,FONT,palette,theme_preference


def fit_position(x, y, width, height, left, top, screen_width, screen_height, margin=10):
    """Keep the help window inside the available virtual desktop rectangle."""
    return (max(left+margin,min(x,left+screen_width-width-margin)),
            max(top+margin,min(y,top+screen_height-height-margin)))


class HoverHelp:
    def __init__(self, root, delay=500):
        self.root=root;self.delay=delay
        self.providers=weakref.WeakKeyDictionary()
        self._pending=None;self._window=None;self._owner=None;self._key=None
        self._spec=None;self._xy=(0,0);self._serial=0
        root.bind('<FocusOut>',lambda e:self.hide(),add='+')
        root.bind('<Unmap>',lambda e:self.hide(),add='+')
        root.bind('<Escape>',lambda e:self.hide(),add='+')

    def attach(self, widget, provider):
        """provider(event) returns a Help or None, including per-row help."""
        self.providers[widget]=provider
        def motion(event):
            if getattr(event,'state',0)&0x1f00:
                self.hide();return
            try:spec=provider(event)
            except (tk.TclError,IndexError,KeyError):spec=None
            self.schedule(widget,spec,event.x_root+16,event.y_root+22)
        widget.bind('<Enter>',motion,add='+')
        widget.bind('<Motion>',motion,add='+')
        for sequence in ('<Leave>','<ButtonPress>','<KeyPress>','<MouseWheel>'):
            widget.bind(sequence,lambda e:self.hide(),add='+')
        widget.bind('<Destroy>',lambda e:self.detach(widget) if e.widget is widget else None,add='+')

    def detach(self,widget):
        self.providers.pop(widget,None)
        if self._owner is widget:self.hide()

    def schedule(self,widget,spec,x,y):
        if spec is None:
            self.hide();return
        key=(str(widget),spec.title,spec.body)
        self._xy=(int(x),int(y))
        if key==self._key:return
        self.hide()
        self._owner=widget;self._spec=spec;self._key=key
        serial=self._serial
        self._pending=self.root.after(self.delay,lambda:self._show(serial))

    def _show(self,serial):
        if serial!=self._serial or self._spec is None:return
        self._pending=None
        try:
            if not self._owner.winfo_exists():self.hide();return
            spec=self._spec
            popup=tk.Toplevel(self._owner,takefocus=False)
            self._window=popup
            popup.withdraw();popup.overrideredirect(True)
            popup.attributes('-topmost',True)
            # No focus_set, grab_set or input binding: help never takes control.
            colors=palette(theme_preference());card=colors['card']
            box=tk.Frame(popup,bg=card,highlightbackground=colors['border'],highlightthickness=1)
            box.pack(fill='both',expand=True)
            width=min(420,max(180,self.root.winfo_vrootwidth()-48))
            tk.Label(box,text=spec.title,bg=card,fg=INK,anchor='w',justify='left',
                     font=('Microsoft YaHei UI',10,'bold'),wraplength=width).pack(fill='x',padx=14,pady=(11,5))
            tk.Label(box,text=spec.body,bg=card,fg=MUTED,anchor='w',justify='left',
                     font=FONT,wraplength=width).pack(fill='x',padx=14,pady=(0,12))
            popup.update_idletasks()
            x,y=fit_position(*self._xy,popup.winfo_reqwidth(),popup.winfo_reqheight(),
                             self.root.winfo_vrootx(),self.root.winfo_vrooty(),
                             self.root.winfo_vrootwidth(),self.root.winfo_vrootheight())
            # At the bottom/right edge, clamping can put the popup under the
            # pointer. Prefer above the pointer so the original control stays clickable.
            px,py=self._xy[0]-16,self._xy[1]-22
            if x<=px<x+popup.winfo_reqwidth() and y<=py<y+popup.winfo_reqheight():
                _,y=fit_position(x,py-popup.winfo_reqheight()-12,popup.winfo_reqwidth(),popup.winfo_reqheight(),
                                 self.root.winfo_vrootx(),self.root.winfo_vrooty(),
                                 self.root.winfo_vrootwidth(),self.root.winfo_vrootheight())
            popup.geometry('%+d%+d'%(x,y));popup.deiconify()
        except tk.TclError:self.hide()

    def hide(self):
        self._serial+=1
        if self._pending is not None:
            try:self.root.after_cancel(self._pending)
            except tk.TclError:pass
            self._pending=None
        if self._window is not None:
            try:self._window.destroy()
            except tk.TclError:pass
            self._window=None
        self._owner=self._spec=self._key=None

    def attach_combobox(self,widget,provider,option_provider):
        self.attach(widget,provider)
        # ttk's choice list is a Tcl-created Listbox rather than a Python widget.
        # Own the callback commands on the combobox so destruction cleans them up.
        popdown=widget.tk.call('ttk::combobox::PopdownWindow',widget)
        path=str(popdown)+'.f.l'
        if not widget.tk.call('winfo','exists',path):return
        def motion(y,xroot,yroot):
            try:
                index=int(widget.tk.call(path,'nearest',int(y)))
                values=widget.cget('values')
                spec=option_provider(str(values[index])) if 0<=index<len(values) else None
                self.schedule(widget,spec,int(xroot)+18,int(yroot)+20)
            except (tk.TclError,ValueError):self.hide()
        command=widget.register(motion)
        widget.tk.call('bind',path,'<Motion>','+'+command+' %y %X %Y')
        for sequence in ('<Leave>','<ButtonPress>','<KeyPress>','<Unmap>'):
            command=widget.register(lambda:self.hide())
            widget.tk.call('bind',path,sequence,'+'+command)

    def attach_menu(self,menu,provider):
        def selected(event=None):
            try:
                index=menu.index('active')
                if index is None or menu.type(index)=='separator':self.hide();return
                spec=provider(menu.entrycget(index,'label'))
                x=menu.winfo_rootx()+menu.winfo_width()+8
                y=menu.winfo_rooty()+menu.yposition(index)
                self.schedule(menu,spec,x,y)
            except tk.TclError:self.hide()
        menu.bind('<<MenuSelect>>',selected,add='+')
        for sequence in ('<Leave>','<ButtonPress>','<KeyPress>','<Unmap>','<Destroy>'):
            menu.bind(sequence,lambda e:self.hide(),add='+')
