const {chromium}=require('playwright'),fs=require('fs'),path=require('path');
(async()=>{
 const root=path.resolve(__dirname,'..'),info=JSON.parse(fs.readFileSync(path.join(root,'.cache/paint_smoke_ready.json'),'utf8'));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader-webgl','--enable-unsafe-swiftshader','--disable-gpu-sandbox']});
 try{
 const page=await browser.newPage({viewport:{width:1084,height:700}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(info.url);await page.waitForFunction(()=>window.previewTest?.report().ready,null,{timeout:30000});
 const first=await page.evaluate(()=>window.previewTest.paintTarget());if(!first)throw Error('no first surface');
 await page.mouse.click(first.x,first.y);await page.locator('#paintFile').setInputFiles(info.image);
 await page.waitForFunction(()=>window.previewTest.paintState().preview);
 const red=await page.evaluate(()=>window.previewTest.paintState());await page.keyboard.press('Control+s');
 let state=await page.evaluate(()=>window.previewTest.paintState());if(state.saved!==1||state.loaded)throw Error('save shortcut failed '+JSON.stringify(state));
 const second=await page.evaluate(p=>window.previewTest.paintTarget(p),first);if(!second)throw Error('no second surface');
 await page.mouse.click(second.x,second.y);await page.locator('#paintFile').setInputFiles(info.blue);
 await page.waitForFunction(()=>window.previewTest.paintState().preview);
 await page.locator('#paintSave').click();state=await page.evaluate(()=>window.previewTest.paintState());if(state.saved!==2)throw Error('second save failed');
 await page.locator('#paintUndo').click();if((await page.evaluate(()=>window.previewTest.paintState())).saved!==1)throw Error('undo failed');
 await page.mouse.click(second.x,second.y);await page.locator('#paintFile').setInputFiles(info.blue);await page.waitForFunction(()=>window.previewTest.paintState().preview);await page.locator('#paintSave').click();
 await page.locator('#paintClear').click();if((await page.evaluate(()=>window.previewTest.paintState())).saved!==2)throw Error('clear removed saved layers');
 await page.locator('#paintName').fill('多张贴图测试成品');
 for(const id of ['paintSave','paintUndo','paintExport','paintName']){const box=await page.locator('#'+id).boundingBox();if(!box||box.x<0||box.x+box.width>1084||box.y+box.height>700)throw Error('control clipped '+id);}
 await page.screenshot({path:path.join(root,'.cache/多图保存验证.png')});
 const responsePromise=page.waitForResponse(r=>r.url().endsWith('/paint')&&r.request().method()==='POST');await page.locator('#paintExport').click();
 const response=await responsePromise,result=await response.json();if(!response.ok())throw Error(JSON.stringify(result));
 if(!result.path.includes('多张贴图测试成品'))throw Error('package name not used');
 const report=JSON.parse(fs.readFileSync(path.join(path.dirname(result.path),'验证记录.json'),'utf8'));
 if(report.layers.length!==2)throw Error('export lost saved images');
 if(errors.length)throw Error(errors.join(';'));
 fs.writeFileSync(path.join(root,'.cache/paint_layers_browser_result.json'),JSON.stringify({result,first,second,red,layers:report.layers,errors},null,2));
 console.log(JSON.stringify({saved:2,shortcut:true,undo:true,namedExport:true,errors}));
 }finally{await browser.close();fs.writeFileSync(path.join(info.folder,'smoke_stop'),'');}
})().catch(e=>{console.error(e);process.exit(1)});
