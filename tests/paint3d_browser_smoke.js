const {chromium}=require('playwright');
(async()=>{
 const [url,file,screenshot]=process.argv.slice(2);
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader-webgl','--enable-unsafe-swiftshader','--disable-gpu-sandbox','--no-sandbox']});
 const page=await browser.newPage({viewport:{width:Number(process.env.PAINT_TEST_WIDTH||1280),height:Number(process.env.PAINT_TEST_HEIGHT||850)}});
 const failures=[];page.on('pageerror',e=>failures.push(String(e)));page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('404 (Not Found)'))failures.push('console: '+m.text())});
 try{
  await page.goto(url,{waitUntil:'domcontentloaded'});
  try{await page.waitForFunction(()=>window.previewTest?.report().ready,null,{timeout:15000});}
  catch(e){console.error('DIAGNOSTIC',JSON.stringify(await page.evaluate(()=>({message:document.querySelector('#message')?.textContent,report:window.previewTest?.report(),paint:window.previewTest?.paintState(),gl:!!document.createElement('canvas').getContext('webgl2',{antialias:true,alpha:false,powerPreference:'high-performance'})}))),JSON.stringify(failures));throw e;}
  await page.waitForTimeout(1500);
  const target=await page.evaluate(()=>window.previewTest.paintTarget());
  if(!target)throw Error('no visible click target');
  await page.mouse.click(target.x,target.y);
  let state=await page.evaluate(()=>window.previewTest.paintState());
  if(!state.placed||state.loaded)throw Error('click before image failed '+JSON.stringify(state));
  await page.locator('#paintFile').setInputFiles(file);
  await page.waitForFunction(()=>window.previewTest.paintState().preview,null,{timeout:10000});
  await page.locator('#paintScale').fill('0.35');await page.locator('#paintScale').dispatchEvent('input');
  await page.locator('#paintAngle').fill('30');await page.locator('#paintAngle').dispatchEvent('input');
  state=await page.evaluate(()=>window.previewTest.paintState());
  if(!state.pixel||state.pixel[0]<180)throw Error('preview pixel not painted '+JSON.stringify(state));
  await page.screenshot({path:screenshot});
  const png=await page.evaluate(()=>window.previewTest.capturePaintTexture());
  require('fs').writeFileSync(screenshot.replace('.png','_贴图.png'),Buffer.from(png.split(',')[1],'base64'));
  const request=page.waitForResponse(r=>r.url().endsWith('/paint')&&r.request().method()==='POST');
  await page.locator('#paintExport').click();const response=await request;const result=await response.json();
  if(!response.ok())throw Error('export failed: '+JSON.stringify(result));
  if(failures.length)throw Error('page errors: '+failures.join(';'));
  console.log(JSON.stringify({state,result,errors:failures}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack||e);process.exit(1)});
