# -*- coding: utf-8 -*-
"""In-game vehicle rules and cosmetic selection, shared by EU and ASIA.

Only the cosmetic getter is wrapped. No visibility, collision, spotting, aiming,
input, network or anti-cheat interfaces are changed. Worker threads use ordinary
file APIs only. Engine/UI calls run on BigWorld's main-thread callback.
"""
from __future__ import unicode_literals
import logging,threading
try:
    import Queue as queue
except ImportError:
    import queue
from .catalog import Catalog,Paused,NATIONS,find_root,sha

LOG=logging.getLogger('LocalSkinFilter2')
LINK='local_skin_filter2'
MODES=[u'不屏蔽',u'仅敌车',u'仅队友',u'敌车和队友']
NATION_LABELS={'german':u'德国','french':u'法国','american':u'美国','british':u'英国',
 'russian':u'苏联','chinese':u'中国','japanese':u'日本','czech':u'捷克',
 'polish':u'波兰','swedish':u'瑞典','italian':u'意大利'}
_controller=None
_installed=False
_contexts=[]


def variable(key):
    return 'v_'+sha(key.encode('utf-8'))[:20]


def car_key(desc,models):
    name=getattr(getattr(desc,'type',None),'name',None)or getattr(desc,'name',None)
    if isinstance(name,type(u''))or isinstance(name,str):
        if ':'in name:
            nation,code=name.split(':',1);nation=nation.lower()
            for resource,definition in NATIONS.items():
                if nation==definition:nation=resource;break
            return nation+'/'+code.lower()
    keys=set('/'.join(p.replace('\\','/').lower().split('/')[1:3])for p in models
             if isinstance(p,(str,type(u'')))and p.lower().startswith('vehicles/')and len(p.split('/'))>3)
    return next(iter(keys))if len(keys)==1 else None


def team_scope(world,vehicle_id):
    """0 bypass, 1 enemy, 2 ally; own/spectator/unknown modes always bypass."""
    try:
        player=world.player()
        if player is None or vehicle_id is None:return 0
        own=getattr(player,'playerVehicleID',None)
        if own is None or own<=0 or own==vehicle_id or player.isObserver():return 0
        team=getattr(player,'team',None);arena=getattr(player,'arena',None)
        row=getattr(arena,'vehicles',{}).get(vehicle_id)
        if not isinstance(row,dict)or team not in(1,2)or row.get('team')not in(1,2):return 0
        return 2 if row['team']==team else 1
    except Exception:return 0


def wrap_context(original,identify):
    def guarded(appearance,*args,**kwargs):
        _contexts.append(identify(appearance,args,kwargs))
        try:return original(appearance,*args,**kwargs)
        finally:_contexts.pop()
    return guarded


class Controller(object):
    def __init__(self,api,world,resmgr,root=None,notify=None,localize=None,panel_factory=None):
        self.api=api;self.world=world;self.resmgr=resmgr;self.root=root
        self.notify=notify or(lambda text:None);self.localize=localize or(lambda key:key)
        saved=api.getModData(LINK,2,dict(enabled=True,rules={}))
        self.enabled=saved.get('enabled')is True if isinstance(saved,dict)else True
        self.rules=dict(saved.get('rules',{}))if isinstance(saved,dict)and isinstance(saved.get('rules'),dict)else{}
        self.ready={};self.catalog=None;self.error=None
        self.events=queue.Queue();self.cancel=threading.Event();self.busy=False;self.stopped=False
        self.attempted=set();self.callbacks={};self.progress=u'正在读取本区客户端车型…';self.job_id=None
        self.panel_factory=panel_factory;self.panel=None;self.ui_rows=[];self.revision=0;self.panel_signature=None
        self.last_ticket=0;self.command_message='';self.command_error=''

    def in_battle(self):
        try:return getattr(self.world.player(),'arena',None)is not None
        except Exception:return False

    def register(self,link,template,callback):
        old=self.callbacks.get(link)
        if old is not None:self.api.onSettingsChanged-=old
        saved=self.api.getModSettings(link,template)
        if saved is not None:self.api.registerCallback(link,callback)
        else:saved=self.api.setModTemplate(link,template,callback)
        if not isinstance(saved,dict):raise ValueError('ModsSettings API did not register '+link)
        self.callbacks[link]=callback;return saved

    def main_template(self):
        ready=sum(1 for key,mode in self.rules.items()if mode and key in self.ready)
        selected=sum(1 for mode in self.rules.values()if mode)
        region=(self.catalog.realm+' '+self.catalog.version)if self.catalog else u'欧服／亚服 2.4.1.1'
        return dict(modDisplayName=u'本地涂装屏蔽 · 状态',column1=[
          dict(type='Label',text=u'恢复选中车型的原版外观；自己的车辆不变。'),
          dict(type='Label',text=u'从模组列表打开“搜索与框选”窗口。'),
          dict(type='Label',text=u'总开关位于选车窗口右上角。'),
          dict(type='Label',text=u'支持搜索、国家筛选、拖框多选和全部敌车。'),
          dict(type='Label',text=u'保存后返回车库，自动准备资源。无需桌面工具。'),
          dict(type='Label',text=u'状态：'+self.progress)],column2=[
          dict(type='Label',text=region),dict(type='Label',text=u'已选择 %d 款，已准备 %d 款'%(selected,ready)),
          dict(type='Label',text=u'准备完成后下次正常加载车辆生效。'),
          dict(type='Label',text=u'首次准备后若提示重启，请重启游戏一次。'),
          dict(type='Label',text=u'待实测；UML／AE 独立挂载物暂不保证屏蔽。')])

    def on_global(self,link,values):
        if link!=LINK or not isinstance(values,dict)or'enabled'not in values:return
        enabled=values.get('enabled')is True
        if enabled!=self.enabled:self.enabled=enabled;self.persist()

    def persist(self):
        self.api.saveModData(LINK,2,dict(enabled=self.enabled,rules=dict(self.rules)))
        self.revision+=1

    def refresh_main(self):
        if self.stopped:return
        try:self.register(LINK,self.main_template(),self.on_global)
        except Exception:LOG.exception('Settings status refresh failed')

    def register_cars(self):
        # Localize on the game thread before publishing a data-only UI snapshot.
        rows=[]
        for car in self.catalog.cars:
            label=car['label']
            if car.get('localization'):
                try:
                    localized=self.localize(car['localization'])
                    if isinstance(localized,str)and not isinstance(localized,type(u'')):localized=localized.decode('utf-8','replace')
                    if localized and not localized.startswith('#'):label=localized
                except Exception:pass
            rows.append(dict(key=car['key'],label=label,code=car['code'],nation=car['nation'],nationLabel=NATION_LABELS.get(car['nation'],car['nation'])))
        self.ui_rows=rows;self.revision+=1

    def submit(self,ticket,value):
        # The browser server never writes settings or calls engine interfaces.
        self.events.put(('command',ticket,value))

    def apply_command(self,ticket,value):
        try:
            if self.in_battle():raise ValueError(u'请返回车库后再修改。')
            known=set(row['key']for row in self.ui_rows);kind=value.get('kind')
            if kind=='enabled':
                enabled=value.get('enabled')
                if not isinstance(enabled,bool):raise ValueError(u'开关值无效。')
                self.enabled=enabled;self.persist();message=u'插件已'+(u'启用。'if enabled else u'关闭。')
            else:
                if not known:raise ValueError(u'车型尚未读取完成，请稍候。')
                mode=value.get('mode');keys=value.get('keys')
                if kind=='all_enemies':keys=sorted(known);mode=1
                elif kind!='rules':raise ValueError(u'操作无效。')
                if not isinstance(keys,list)or not keys or len(keys)>5000:raise ValueError(u'请选择车型。')
                if isinstance(mode,bool)or not isinstance(mode,int)or mode not in(0,1,2,3):raise ValueError(u'屏蔽范围无效。')
                chosen=set(keys)
                if not chosen.issubset(known):raise ValueError(u'车型已变化，请重新打开窗口。')
                updated=dict(self.rules)
                for key in chosen:
                    if updated.get(key,0)!=mode:self.attempted.discard(key)
                    updated[key]=mode
                self.rules=updated
                if kind=='all_enemies':self.enabled=True
                self.persist();message=u'已保存 %d 款车型：%s。'%(len(chosen),MODES[mode])
            self.command_message=message;self.command_error=''
        except (ValueError,TypeError,KeyError)as error:
            self.command_error=type(u'')(error);self.command_message=''
        self.last_ticket=max(self.last_ticket,ticket);self.revision+=1

    def update_panel(self):
        if self.panel is None:return
        signature=(self.revision,self.progress,self.enabled,len(self.ready),self.last_ticket,self.busy)
        if signature==self.panel_signature:return
        affected=getattr(self.catalog,'overridden',set())if self.catalog else set()
        cars=[dict(row,overridden=row['key']in affected,prepared=row['key']in self.ready)for row in self.ui_rows]
        countries={row['nation']:row['nationLabel']for row in self.ui_rows}
        self.panel.update(dict(loading=self.catalog is None,cars=cars,rules=dict(self.rules),enabled=self.enabled,
          nations=[dict(key=key,label=value)for key,value in sorted(countries.items())],revision=self.revision,
          realm=self.catalog.realm if self.catalog else'',version=self.catalog.version if self.catalog else'',
          progress=self.progress,overrideCount=len(affected),appliedTicket=self.last_ticket,
          commandMessage=self.command_message,commandError=self.command_error))
        self.panel_signature=signature

    def open_selector(self):
        if self.in_battle():self.inform(u'请在车库打开搜索与框选窗口。');return
        try:
            if self.panel is None:
                factory=self.panel_factory
                if factory is None:
                    from .gameface import GamefacePanel
                    factory=GamefacePanel
                self.panel=factory(self);self.panel_signature=None
            self.update_panel();self.panel.show()
        except Exception:
            LOG.exception('In-game selector unavailable')
            self.inform(u'选车窗口未能打开，原设置保持不变。')

    def begin(self):
        self.refresh_main()
        self.api.onWindowOpened+=self.refresh_main
        self.busy=True
        def read_catalog():
            try:self.events.put(('catalog',Catalog(self.root or find_root()).scan()))
            except Exception as error:self.events.put(('fatal',error))
        worker=threading.Thread(target=read_catalog);worker.daemon=True;worker.start()
        self.job_id=self.world.callback(0.25,self.poll)

    def poll(self):
        if self.stopped:return
        battle=self.in_battle()
        if battle and self.panel is not None:self.panel.close()
        if battle or not self.enabled:self.cancel.set()
        try:
            while True:
                item=self.events.get_nowait();kind=item[0]
                if kind=='catalog':
                    self.catalog=item[1];self.busy=False;self.register_cars();self.progress=u'请选择车型并保存。';self.refresh_main()
                elif kind=='fatal':
                    self.busy=False;self.error=item[1];self.progress=u'客户端不支持或读取失败，请查看日志。'
                    LOG.error('Catalog unavailable: %s',item[1]);self.refresh_main()
                elif kind=='progress':self.progress=item[1]
                elif kind=='command':self.apply_command(item[1],item[2])
                elif kind=='ready':
                    self.busy=False
                    if battle:self.events.put(item);break
                    key,record=item[1:];self.publish(key,record)
                elif kind=='paused':self.busy=False;self.attempted.discard(item[1]);self.progress=u'准备已暂停；启用插件并返回车库后继续。'
                elif kind=='failed':
                    self.busy=False;key,error=item[1:];self.progress=u'部分车型准备失败，保留原外观。'
                    LOG.error('Private vanilla cache failed for %s: %s',key,error)
                    if not battle:self.inform(u'涂装屏蔽：'+key+u' 准备失败，保持原外观。详见日志。')
        except queue.Empty:pass
        if not battle and not self.busy and self.catalog and self.enabled and not self.error:
            affected=getattr(self.catalog,'overridden',None)
            pending=sorted(key for key,mode in self.rules.items()if mode and(affected is None or key in affected)and key not in self.ready and key not in self.attempted)
            if pending:self.prepare(pending[0])
        self.update_panel()
        self.job_id=self.world.callback(0.5,self.poll)

    def prepare(self,key):
        self.busy=True;self.attempted.add(key);self.cancel.clear();self.progress=u'正在准备：'+key
        def work():
            try:
                record=self.catalog.prepare(key,self.cancel.is_set,lambda s:self.events.put(('progress',s)))
                self.events.put(('ready',key,record))
            except Paused:self.events.put(('paused',key))
            except Exception as error:self.events.put(('failed',key,error))
        worker=threading.Thread(target=work);worker.daemon=True;worker.start()

    def publish(self,key,record):
        try:
            # A private namespace only. If the live filesystem cannot see new
            # files, leave native appearance intact and request a normal restart.
            purge=getattr(self.resmgr,'purge',None)
            if purge:purge('vehicles/_lsf2')
            if not all(self.resmgr.isFile(row['destination'])for row in record['resources']):
                self.progress=u'资源已准备；请重启游戏后生效。'
                self.inform(u'涂装屏蔽：原版资源已准备，请重启游戏一次。');return
            self.ready[key]=dict(record['models']);self.progress=u'已准备：'+key;self.revision+=1
            self.inform(u'涂装屏蔽：'+key+u' 已准备，下次正常加载车辆生效。')
        except Exception:
            LOG.exception('Private resources not exposed by current client')
            self.progress=u'资源已准备，当前会话保持原外观；请重启。'

    def inform(self,text):
        try:self.notify(text)
        except Exception:LOG.exception('Optional garage notification failed')

    def select(self,desc,models,scope):
        if not self.enabled or scope not in(1,2):return models
        key=car_key(desc,models);mode=self.rules.get(key,0)
        if mode not in(scope,3):return models
        mapping=self.ready.get(key)
        if not mapping:return models
        mapped=[mapping.get(p.replace('\\','/').lower(),p)if isinstance(p,(str,type(u'')))else p for p in models]
        if list(models)==mapped:return models
        if hasattr(models,'_fields'):return type(models)(*mapped)
        return tuple(mapped)if isinstance(models,tuple)else mapped

    def stop(self):
        self.stopped=True;self.cancel.set()
        if self.panel is not None:self.panel.stop();self.panel=None
        if self.job_id is not None:
            try:self.world.cancelCallback(self.job_id)
            except Exception:pass
        # Worker-owned ZIP handles are not closed while it may still be reading.


def install_hooks(controller,assembler,common,compound):
    old_paths=assembler.getPartModelsFromDesc;old_prereqs=common.prerequisites
    refresh_name='_CompoundAppearance__requestModelsRefresh';old_refresh=getattr(compound,refresh_name)
    def part_models(*args,**kwargs):
        models=old_paths(*args,**kwargs)
        if not _contexts:return models
        desc=args[0]if args else kwargs.get('vehicleDesc')
        return controller.select(desc,models,_contexts[-1])
    assembler.getPartModelsFromDesc=part_models
    common.prerequisites=wrap_context(old_prereqs,lambda a,args,kw:team_scope(controller.world,args[0]if args else kw.get('vID')))
    setattr(compound,refresh_name,wrap_context(old_refresh,lambda a,args,kw:team_scope(controller.world,getattr(a,'_CommonTankAppearance__vID',None))))


def init():
    global _controller,_installed
    if _installed:return
    try:
        import BigWorld,ResMgr
        from gui.modsSettingsApi import g_modsSettingsApi
        from gui.modsListApi import g_modsListApi
        from vehicle_systems import model_assembler
        from vehicle_appearance.common_tank_appearance import CommonTankAppearance
        from vehicle_systems.CompoundAppearance import CompoundAppearance
        from gui import SystemMessages
        from helpers import i18n
        controller=Controller(g_modsSettingsApi,BigWorld,ResMgr,
          notify=lambda text:SystemMessages.pushMessage(text.encode('utf-8'),type=SystemMessages.SM_TYPE.Information),localize=i18n.makeString)
        # Fail before installing hooks if the ordinary settings API is absent.
        controller.begin()
        install_hooks(controller,model_assembler,CommonTankAppearance,CompoundAppearance)
        g_modsListApi.addModification(id='local_skin_filter_selector',name=u'本地涂装屏蔽 · 搜索与框选',
          description=u'搜索、国家筛选、鼠标拖框与批量屏蔽敌我涂装。',icon='gui/maps/icons/modsSettingsApi/icon.png',enabled=True,login=False,lobby=True,callback=controller.open_selector)
        _controller=controller;_installed=True
        LOG.info('In-game cosmetic filter 2.1.2 loaded; native Gameface EU/ASIA adapter. Game validation: not_tested.')
    except Exception:LOG.exception('In-game cosmetic filter unavailable; keep native appearance')


def fini():
    if _controller is not None:_controller.stop()
