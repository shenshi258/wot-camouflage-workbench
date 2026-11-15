"""Real headless Chromium interaction checks for our own in-game browser page.

Starts a private loopback UI and a separate empty browser profile. Does not
start the game, use the user's browser profile, or write into the game folder.
"""
import argparse,hashlib,json,os,subprocess,sys,tempfile,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

NODE=r'''
import fs from 'node:fs';
const cfg=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const nap=ms=>new Promise(r=>setTimeout(r,ms));
const targets=await(await fetch('http://127.0.0.1:'+cfg.port+'/json/list')).json();
const ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
let id=0,pending=new Map(),errors=[];
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){let p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);};
function call(method,params={}){return new Promise((resolve,reject)=>{const n=++id;const timer=setTimeout(()=>{pending.delete(n);reject(Error('CDP timeout: '+method));},10000);pending.set(n,{resolve,reject,timer});ws.send(JSON.stringify({id:n,method,params}));});}
async function value(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;}
async function until(expression){for(let n=0;n<80;n++){if(await value(expression))return;await nap(100);}throw Error('Condition failed: '+expression);}
async function click(id){const b=await value(`(()=>{const r=document.getElementById(${JSON.stringify(id)}).getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await call('Input.dispatchMouseEvent',{type:'mousePressed',x:b.x,y:b.y,button:'left',clickCount:1});await call('Input.dispatchMouseEvent',{type:'mouseReleased',x:b.x,y:b.y,button:'left',clickCount:1});}
async function change(id,v){if(id==='search'){await value(`(()=>{let e=document.getElementById('search');e.value=${JSON.stringify(v)};e.dispatchEvent(new Event('input',{bubbles:true}));})()`);return;}await click(id);let option=await value(`(()=>{let old=document.getElementById('test-choice');if(old)old.removeAttribute('id');let e=Array.from(document.querySelectorAll('#${id}-choices button')).find(e=>e.getAttribute('data-value')===${JSON.stringify(v)});e.id='test-choice';return !!e})()`);assert(option,'dropdown option missing');await click('test-choice');}

async function dragRows(first,last,ctrl=false){const r=await value(`(()=>{let a=document.querySelectorAll('.car-row')[${first}].getBoundingClientRect(),b=document.querySelectorAll('.car-row')[${last}].getBoundingClientRect();return{x1:a.left+75,y1:a.top+7,x2:b.left+310,y2:b.bottom-7}})()`);await call('Input.dispatchMouseEvent',{type:'mousePressed',x:r.x1,y:r.y1,button:'left',clickCount:1,modifiers:ctrl?2:0});for(let n=1;n<=12;n++)await call('Input.dispatchMouseEvent',{type:'mouseMoved',x:r.x1+(r.x2-r.x1)*n/12,y:r.y1+(r.y2-r.y1)*n/12,buttons:1,modifiers:ctrl?2:0});await call('Input.dispatchMouseEvent',{type:'mouseReleased',x:r.x2,y:r.y2,button:'left',clickCount:1,modifiers:ctrl?2:0});}
function assert(ok,msg){if(!ok)throw Error(msg);}
await call('Page.enable');await call('Runtime.enable');
// Test the delivered native-ViewModel branch. Only this development adapter
// talks to the isolated test server; the installed game view has no listener.
await call('Page.addScriptToEvaluateOnNewDocument',{source:`
window.__nativeCommands=0;window.__ticketMap={};
function devRequest(data){return fetch('/api/'+(data?'command':'state'),{method:data?'POST':'GET',headers:{'X-LSF-Key':${JSON.stringify(cfg.url.split('#')[1])},'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined}).then(r=>r.json()).then(function(r){if(!data&&r.appliedTicket)r.appliedTicket=window.__ticketMap[r.appliedTicket]||0;return r;});}
window.model={payload:'{}',onCommand:function(args){window.__nativeCommands++;var value=JSON.parse(args.payload);devRequest(value.command).then(r=>window.__ticketMap[r.ticket]=value.ticket);},onClose:function(){window.__nativeClosed=true;}};
window.engine={whenReady:devRequest().then(function(state){window.model.payload=JSON.stringify(state);setInterval(function(){devRequest().then(s=>window.model.payload=JSON.stringify(s));},90);})};
`});
await call('Emulation.setDeviceMetricsOverride',{width:1120,height:780,deviceScaleFactor:1,mobile:false});await call('Page.navigate',{url:cfg.url});
await until("Number(document.getElementById('rows').getAttribute('data-total'))>1000");let checks=[];assert(await value("document.querySelectorAll('.car-row').length<40"),'virtual list created too many rows');checks.push('1000 vehicle list renders fewer than 40 rows');
await value("window.__firstRow=document.querySelector('.car-row')");await nap(1100);assert(await value("window.__firstRow===document.querySelector('.car-row')"),'unchanged payload rebuilt the list');checks.push('unchanged payload retains row elements');
await change('search','g197');await until("document.querySelectorAll('.car-row').length===1");assert(await value("document.querySelector('.car-row').dataset.key.includes('g197')"),'search code mismatch');checks.push('name/code search');
await change('search','no-match-test-xyz');assert(await value("document.querySelectorAll('.car-row').length===0"),'empty search');checks.push('empty search');
await change('search','');await change('nation','german');assert(await value("Array.from(document.querySelectorAll('.car-row')).every(e=>e.dataset.key.startsWith('german/'))"),'country filter');checks.push('country filter');
await dragRows(0,3);assert(await value("document.querySelectorAll('.car-row.selected').length===4"),'rectangle selection not four rows');checks.push('mouse rectangle selects four rows');
await dragRows(5,6,true);assert(await value("document.querySelectorAll('.car-row.selected').length===6"),'Ctrl drag did not append');checks.push('Ctrl rectangle appends');
await change('mode','2');await click('apply');await until("!document.getElementById('apply').disabled");assert(await value("Array.from(document.querySelectorAll('.car-row.selected .mode')).every(e=>e.textContent==='仅队友')"),'batch modes not saved');checks.push('batch ally setting');
await click('clear-selection');assert(await value("document.querySelectorAll('.car-row.selected').length===0"),'clear selection');
await click('select-all');assert(await value("Number(document.getElementById('selection-count').textContent.match(/[0-9]+/)[0])===Number(document.getElementById('rows').getAttribute('data-total'))"),'select filtered must include rows outside the viewport');checks.push('select all filtered country');
await value("document.getElementById('viewport').scrollTop=4200");await until("Number(document.querySelector('.car-row').getAttribute('data-index'))>30");assert(await value("document.querySelectorAll('.car-row').length<40&&Array.from(document.querySelectorAll('.car-row')).every(e=>e.classList.contains('selected'))"),'selection was lost when virtual rows were recycled');checks.push('recycled rows retain selections outside viewport');
await change('nation','french');assert(await value("document.getElementById('selection-count').textContent.includes('当前结果 0')"),'hidden selection not retained');checks.push('selection retained across filters');
await click('all-enemies');await until("!document.getElementById('all-enemies').disabled");await change('nation','');assert(await value("Array.from(document.querySelectorAll('.car-row .mode')).every(e=>e.textContent==='仅敌车')"),'global enemy quick action');checks.push('all enemy across every country');
await click('clear-selection');await value("document.getElementById('viewport').scrollTop=0");
const edge=await value("(()=>{let r=document.getElementById('viewport').getBoundingClientRect();return{x:r.left+90,y:r.top+10,bottom:r.bottom-3}})()");
await call('Input.dispatchMouseEvent',{type:'mousePressed',x:edge.x,y:edge.y,button:'left',clickCount:1});await call('Input.dispatchMouseEvent',{type:'mouseMoved',x:edge.x+190,y:edge.bottom,buttons:1});await nap(650);await call('Input.dispatchMouseEvent',{type:'mouseReleased',x:edge.x+190,y:edge.bottom,button:'left',clickCount:1});assert(await value("document.getElementById('viewport').scrollTop>0&&document.querySelectorAll('.car-row.selected').length>10"),'drag auto scroll');checks.push('drag scroll selects off-screen rows');
await change('nation','german');await change('search','pz');await click('clear-selection');await value("document.getElementById('viewport').scrollTop=0");await dragRows(0,4);
let shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(cfg.screenshot,Buffer.from(shot.data,'base64'));
await call('Emulation.setDeviceMetricsOverride',{width:800,height:600,deviceScaleFactor:1,mobile:false});
assert(await value("(()=>{let b=document.getElementById('apply').getBoundingClientRect(),v=document.getElementById('viewport').getBoundingClientRect();return b.right<=innerWidth&&b.bottom<=innerHeight&&v.height>=80})()"),'compact layout clips actions');checks.push('800x600 layout keeps actions visible');
assert(await value('window.__nativeCommands>0'),'native ViewModel commands were not used');checks.push('native ViewModel command branch');
await click('close');assert(await value('window.__nativeClosed===true'),'native close command');checks.push('native close command');
assert(errors.length===0,'Browser exceptions: '+errors.join(';'));
fs.writeFileSync(cfg.result,JSON.stringify({status:'passed',checks,game_browser_rendering:'not_tested'},null,2));ws.close();
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--client',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--html',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(ROOT/'game_mods'))
    from local_skin_filter.catalog import Catalog
    from local_skin_filter.runtime import Controller
    from local_skin_filter.selector import PanelServer
    from local_skin_filter.test_runtime import API
    from types import SimpleNamespace
    catalog=Catalog(str(a.client)).scan();world=SimpleNamespace(player=lambda:None,callback=lambda *args:1,cancelCallback=lambda *args:None)
    controller=Controller(API(),world,SimpleNamespace());controller.catalog=catalog;controller.register_cars();controller.busy=True
    html=a.html.read_bytes()if a.html else(ROOT/'game_mods/local_skin_filter/selector.html').read_bytes()
    controller.panel=PanelServer(controller.submit,html=html)
    controller.update_panel()
    profile=a.output/('chrome_profile_'+uuid.uuid4().hex[:8]);profile.mkdir()
    browser=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    proc=subprocess.Popen([str(browser),'--headless=new','--remote-debugging-port=0','--user-data-dir='+str(profile.resolve()),
        '--disable-extensions','--disable-background-networking','--no-first-run','--no-default-browser-check','--disable-sync','about:blank'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
    node=None
    try:
        port_file=profile/'DevToolsActivePort'
        for n in range(100):
            if port_file.is_file():break
            time.sleep(.1)
        port=int(port_file.read_text().splitlines()[0])
        config=a.output/'browser_config.json';result=a.output/'browser_result.json';script=a.output/'browser_check.mjs'
        config.write_text(json.dumps(dict(port=port,url=controller.panel.url,screenshot=str((a.output/'搜索与拖框.png').resolve()),result=str(result.resolve()))),encoding='utf-8')
        script.write_text(NODE,encoding='utf-8')
        node=subprocess.Popen(['C:/Program Files/nodejs/node.exe',str(script.resolve()),str(config.resolve())],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=0x08000000)
        deadline=time.monotonic()+90
        while node.poll()is None and time.monotonic()<deadline:
            controller.poll();time.sleep(.08)
        if node.poll()is None:node.terminate();raise RuntimeError('Browser check timed out')
        output=node.stdout.read().decode('utf-8','replace');(a.output/'browser_stdout.txt').write_text(output,encoding='utf-8')
        if node.returncode:raise RuntimeError(output)
        final=json.loads(result.read_text());final['html_sha256']=hashlib.sha256(controller.panel.html).hexdigest()
        result.write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8');print(result.read_text())
    finally:
        if node is not None and node.poll()is None:node.terminate()
        controller.stop();catalog.close();proc.terminate();proc.wait(timeout=10)


if __name__=='__main__':main()
