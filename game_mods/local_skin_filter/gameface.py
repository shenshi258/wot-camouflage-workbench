# -*- coding: utf-8 -*-
"""Native WG 2.4.1 Gameface view. No CEF navigation or HTTP listener."""
from __future__ import unicode_literals
import json
from frameworks.wulf import ViewModel,ViewSettings,ViewFlags,WindowFlags,WindowLayer
from gui.impl.gen import R
from gui.impl.pub.view_impl import ViewImpl
from gui.impl.pub.window_impl import WindowImpl
try:
    INTEGER_TYPES=(int,long)
except NameError:
    INTEGER_TYPES=(int,)


class SelectorModel(ViewModel):
    def __init__(self):
        super(SelectorModel,self).__init__(properties=1,commands=2)

    def _initialize(self):
        super(SelectorModel,self)._initialize()
        self._addStringProperty('payload','{}')
        self.onCommand=self._addCommand('onCommand')
        self.onClose=self._addCommand('onClose')

    def setPayload(self,value):self._setString(0,value)


class SelectorView(ViewImpl):
    def __init__(self,bridge):
        self.bridge=bridge
        settings=ViewSettings(R.mods.local_skin_filter.views.Selector())
        settings.flags=ViewFlags.VIEW;settings.model=SelectorModel()
        super(SelectorView,self).__init__(settings)

    @property
    def viewModel(self):
        # ViewImpl exposes getViewModel(), not a viewModel attribute. Native
        # generated views provide this property themselves.
        return super(SelectorView,self).getViewModel()

    def _getEvents(self):
        return ((self.viewModel.onCommand,self.bridge.command),
                (self.viewModel.onClose,self.bridge.close))

    def _onLoading(self,*args,**kwargs):
        super(SelectorView,self)._onLoading(*args,**kwargs)
        self.bridge.view=self;self.bridge.push()

    def _finalize(self):
        bridge=self.bridge
        if bridge.view is self:bridge.view=None;bridge.window=None
        super(SelectorView,self)._finalize()


class GamefacePanel(object):
    def __init__(self,controller):
        self.controller=controller;self.view=None;self.window=None
        self.state='{}';self.ticket=controller.last_ticket

    def update(self,state):
        self.state=json.dumps(state,ensure_ascii=True)
        self.push()

    def push(self):
        if self.view is not None:
            with self.view.viewModel.transaction()as model:model.setPayload(self.state)

    def show(self):
        if self.window is not None:return
        # WG registers the namespaced layout from gui/gen_resources at startup.
        # Native resources work on both EU and ASIA without changing any list of
        # allowed browser sites or replacing a shared UI resource.
        view=SelectorView(self)
        self.window=WindowImpl(WindowFlags.WINDOW|WindowFlags.WINDOW_FULLSCREEN|WindowFlags.WINDOW_MODAL,
          content=view,layer=WindowLayer.TOP_WINDOW)
        self.window.load()

    def command(self,args):
        # WULF invokes this handler on the game thread. Reuse the controller's
        # queue so persistence and resource preparation keep their usual order.
        try:
            raw=args.get('payload','')
            if not isinstance(raw,(str,type(u'')))or not 0<len(raw)<=256*1024:raise ValueError('size')
            value=json.loads(raw);ticket=value['ticket'];command=value['command']
            if isinstance(ticket,bool)or not isinstance(ticket,INTEGER_TYPES)or not self.ticket<ticket<=9007199254740991:raise ValueError('ticket')
            if not isinstance(command,dict):raise ValueError('command')
            self.ticket=ticket;self.controller.submit(self.ticket,command)
        except (ValueError,TypeError,KeyError,AttributeError):
            self.controller.inform(u'选车指令无效，请重新打开窗口。')

    def close(self,*args):
        window=self.window;self.window=None;self.view=None
        if window is not None:window.destroy()

    def stop(self):self.close()
