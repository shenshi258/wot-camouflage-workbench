// Headless Chromium/CDP: exercise actual file inputs, persistent thumbnails,
// metadata edits, recycle/undo, and use the selected asset in a model export.
const fs=require('fs'),path=require('path'),cp=require('child_process'),assert=require('assert');
const root=path.resolve(__dirname,'..'),python=process.argv[2];
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let server,browser,info,send,ws;
async function until(fn,timeout=30000){const deadline=Date.now()+timeout;while(Date.now()<deadline){const result=await fn();if(result)return result;await delay(100);}throw Error('Browser check timed out');}
async function start(){
 server=cp.spawn(python,['-B',path.join(__dirname,'library_browser_server.py'),...(process.argv.includes('--scope')?['--scope']:[])],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
 let output='',stderr='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>stderr+=chunk);
 await until(()=>{if(server.exitCode!==null)throw Error(stderr);return output.includes('LIBRARY_BROWSER_READY');});
 info=JSON.parse(fs.readFileSync(path.join(root,'.cache/library38_browser_ready.json'),'utf8'));
 const profile=path.join(root,'.cache','library38_chrome_'+Date.now());
 browser=cp.spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--remote-debugging-port=0','--remote-allow-origins=*','--user-data-dir='+profile,'--no-first-run','--no-default-browser-check','--enable-webgl','--use-gl=angle','--use-angle=swiftshader-webgl','--enable-unsafe-swiftshader','--disable-gpu-sandbox','about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
 let chromeOutput='';browser.stderr.on('data',chunk=>chromeOutput+=chunk);
 const endpoint=await until(()=>chromeOutput.match(/DevTools listening on (ws:\/\/[^\s]+)/)?.[1]);
 const port=new URL(endpoint).port,targets=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 ws=new WebSocket(targets.find(target=>target.type==='page').webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 const pending=new Map();let serial=0;
 ws.addEventListener('message',event=>{const message=JSON.parse(event.data);if(!message.id)return;const job=pending.get(message.id);if(!job)return;pending.delete(message.id);clearTimeout(job.timer);message.error?job.reject(Error(JSON.stringify(message.error))):job.resolve(message.result);});
 ws.addEventListener('close',()=>{for(const job of pending.values()){clearTimeout(job.timer);job.reject(Error('Browser closed'));}pending.clear();});
 send=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject,timer:setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000)});ws.send(JSON.stringify({id,method,params}));});
 await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1084,height:700,deviceScaleFactor:1,mobile:false});
}
async function evaluate(expression){if(expression.includes('await '))expression='(async()=>{'+expression+'})()';const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text+' '+JSON.stringify(result.exceptionDetails.exception));return result.result.value;}
async function screenshot(name){const result=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(root,'.cache',name),Buffer.from(result.data,'base64'));}
async function reviewLibrary(){
 await evaluate(`
  const library=window.assetLibrary,originalUse=library.onUse,originalFetch=window.fetch;
  const first=library.items[0],second=library.items[1],used=[];let release;
  library.onUse=async(blob,item)=>{used.push(item.id);return true;};
  window.fetch=(url,options)=>String(url).endsWith('/library/image/'+first.id)?new Promise(resolve=>{release=()=>originalFetch(url,options).then(resolve);}):originalFetch(url,options);
  try{library.select(first);const earlier=library.use();library.select(second);await library.use();await release();await earlier;window.qaUsed=used;window.qaExpected=second.id;}
  finally{library.onUse=originalUse;window.fetch=originalFetch;}
 `);
 assert.deepStrictEqual(await evaluate('window.qaUsed'),[await evaluate('window.qaExpected')]);
 await evaluate(`window.qaOriginal={name:assetLibrary.selected.name,category:assetLibrary.selected.category};assetLibrary.el('name').value='长名称'.repeat(30);assetLibrary.el('editCategory').value='长分类'.repeat(13);await assetLibrary.edit();`);
 for(const size of [[800,600],[1084,700]])for(const glass of [false,true]){
  await send('Emulation.setDeviceMetricsOverride',{width:size[0],height:size[1],deviceScaleFactor:1,mobile:false});
  const result=await evaluate(`(()=>{document.body.classList.toggle('glass-ui',${glass});const library=assetLibrary;return {colour:getComputedStyle(library.el('import')).backgroundColor,nameHeight:library.el('chosenName').getBoundingClientRect().height,wide:document.documentElement.scrollWidth>innerWidth+1,help:library.el('remove').title};})()`);
  assert.strictEqual(result.colour,'rgb(0, 122, 255)');assert(result.nameHeight<=40);assert(!result.wide);assert(result.help.includes('回收站'));
  if(size[0]===800)await screenshot('素材库_UI复核_'+(glass?'玻璃':'经典')+'_800x600.png');
 }
 await evaluate(`assetLibrary.el('name').value=qaOriginal.name;assetLibrary.el('editCategory').value=qaOriginal.category;await assetLibrary.edit();document.body.classList.remove('glass-ui');`);
 await send('Emulation.setDeviceMetricsOverride',{width:1084,height:700,deviceScaleFactor:1,mobile:false});
}
(async()=>{
 try{
  await start();await send('Page.navigate',{url:info.library_url});await until(()=>evaluate('!!window.assetLibrary'));
  await evaluate(`window.qaErrors=[];window.addEventListener('error',event=>qaErrors.push(event.message));`);
  await evaluate(`(()=>{const transfer=new DataTransfer();const files=${JSON.stringify(info.files)};for(const file of files){transfer.items.add(new File([Uint8Array.from(atob(file.image),c=>c.charCodeAt(0))],file.name,{type:'image/png'}));}transfer.items.add(new File([Uint8Array.from(atob(files[0].image),c=>c.charCodeAt(0))],'重复.png',{type:'image/png'}));transfer.items.add(new File(['broken'],'损坏.jpg',{type:'image/jpeg'}));const input=assetLibrary.el('files');input.files=transfer.files;input.dispatchEvent(new Event('change'));})()`);
  await until(()=>evaluate('assetLibrary.items.length===8&&!assetLibrary.busy'));
  assert((await evaluate("assetLibrary.el('status').textContent")).includes('新增 8，重复 1，失败 1'));
  await evaluate(`assetLibrary.el('search').value='橙色';assetLibrary.el('search').dispatchEvent(new Event('input'));`);
  assert.strictEqual(await evaluate("assetLibrary.el('grid').querySelectorAll('button').length"),1);
  await evaluate(`assetLibrary.el('grid').querySelector('button').click();assetLibrary.el('name').value='<img onerror=alert(1)>';assetLibrary.el('editCategory').value='警示图案';await assetLibrary.edit();`);
  assert.strictEqual(await evaluate("assetLibrary.el('chosenName').querySelectorAll('img').length"),0);
  await evaluate(`assetLibrary.el('name').value='橙色警示';await assetLibrary.edit();await assetLibrary.remove();`);
  assert.strictEqual(await evaluate('assetLibrary.items.length'),7);
  await evaluate('await assetLibrary.restore()');assert.strictEqual(await evaluate('assetLibrary.items.length'),8);
  await evaluate(`assetLibrary.el('search').value='';assetLibrary.el('search').dispatchEvent(new Event('input'));`);
  await screenshot('图片素材库_缩略图验证.png');
  const selected=await evaluate('assetLibrary.selected.id');
  await send('Page.reload');await until(()=>evaluate('!!window.assetLibrary&&assetLibrary.items.length===8'));
  if(process.argv.includes('--review'))await reviewLibrary();
  await send('Page.navigate',{url:info.paint_url});
  await until(()=>evaluate('!!window.previewTest&&window.previewTest.report().ready'),45000);
  if(process.argv.includes('--scope'))assert.strictEqual(await evaluate("document.getElementById('paintScope').value"),'self');
  await evaluate("document.getElementById('paintLibrary').click()");await until(()=>evaluate("document.querySelectorAll('#libraryPanel [data-asset-id]').length===8"));
  await evaluate(`document.querySelector('#libraryPanel [data-asset-id="${selected}"]').click();document.querySelector('#libraryPanel [data-lib="use"]').click();`);
  await until(()=>evaluate('window.previewTest.paintState().loaded'));
  assert((await evaluate("document.querySelector('#libraryPanel .asset-tile img').getBoundingClientRect().height"))>=70);
  await screenshot('三维贴图_自导入素材库验证.png');
  await evaluate("document.querySelector('#libraryPanel [data-lib=close]').click()");
  const target=await evaluate('window.previewTest.paintTarget()');assert(target);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:target.x,y:target.y,button:'left',buttons:1,clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:target.x,y:target.y,button:'left',buttons:0,clickCount:1});
  await until(()=>evaluate('window.previewTest.paintState().preview'));
  await evaluate("document.getElementById('paintSave').click();document.getElementById('paintName').value='图库素材验证';document.getElementById('paintExport').click()");
  await until(()=>evaluate("document.getElementById('paintStatus').textContent.startsWith('待测包已生成')"));
  if(process.argv.includes('--scope')){
   const exported=await evaluate("document.getElementById('paintStatus').textContent.slice('待测包已生成：'.length)");
   const record=JSON.parse(fs.readFileSync(path.join(path.dirname(exported),'验证记录.json'),'utf8'));
   assert.strictEqual(record.application_scope.value,'self');
   assert(Object.keys(record.application_scope.model_paths).length>0);
   assert.strictEqual(record.whole_vehicle_loading.status,'not_tested');
   console.log('PAINT_SCOPE_EXPORT_AND_PERSISTED_SELECTION_OK');
  }
  const result=await evaluate('({paint:window.previewTest.paintState(),errors:window.previewTest.report().errors})');
  assert.strictEqual(result.paint.saved,1);assert.deepStrictEqual(result.errors,[]);
  fs.writeFileSync(path.join(root,'.cache/library38_browser_result.json'),JSON.stringify({scope:'Synthetic media and model only; no actual game execution.',whole_vehicle_loading:{status:'not_tested'},imported:8,duplicate:1,rejected:1,persisted:true,edited:true,recycleUndo:true,selectedAndExported:true,result},null,2));
  console.log('ASSET_LIBRARY_BROWSER_IMPORT_SEARCH_PERSIST_AND_PAINT_EXPORT_OK');
  if(process.argv.includes('--review'))console.log('UI_LIBRARY_THEMES_COMPACT_LAYOUT_AND_LAST_SELECTION_OK');
 }finally{
  if(info)fs.writeFileSync(info.stop,'');
  if(send){await send('Page.navigate',{url:'about:blank'}).catch(()=>{});await send('Browser.close').catch(()=>{});}
  if(ws)ws.close();if(browser&&browser.exitCode===null)browser.kill();
  if(server)await until(()=>server.exitCode!==null,10000).catch(()=>server.kill());
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
