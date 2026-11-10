// Colour input, stale refresh, restore and queued edits using actual handlers.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync(process.argv[2],'utf8');
const a=code.indexOf('let tintTimer='),b=code.indexOf('// 与桌面数值输入保持',a);
assert(a>=0&&b>a);
const elements=Object.fromEntries(['aeTintColor','aeTintStrength','aeTintValue','aeTintReset','message'].map(id=>[id,{value:'',textContent:''}]));
const timers=new Map(),calls=[];let serial=0,response={ok:true};
const context={$:id=>elements[id],document:{activeElement:null},effectInfo:{config:{tint_color:'#FFFFFF',tint_strength:0}},
  setTimeout:fn=>{timers.set(++serial,fn);return serial;},clearTimeout:id=>timers.delete(id),
  post:async(path,values)=>{calls.push([path,JSON.parse(JSON.stringify(values))]);return response;}};
vm.createContext(context);vm.runInContext(code.slice(a,b),context);
async function flush(){const jobs=[...timers.values()];timers.clear();await Promise.all(jobs.map(fn=>fn()));}
(async()=>{
  context.syncTintControls(context.effectInfo.config);
  elements.aeTintColor.value='#00c8ff';elements.aeTintColor.oninput();
  assert.strictEqual(Number(elements.aeTintStrength.value),100);
  context.syncTintControls(context.effectInfo.config); // stale status cannot undo the edit
  assert.strictEqual(elements.aeTintColor.value,'#00c8ff');
  elements.aeTintColor.value='#ff20a0';elements.aeTintColor.oninput();
  assert.strictEqual(timers.size,1);await flush();
  assert.deepStrictEqual(calls.pop(),['effectparams',{tint_color:'#ff20a0',tint_strength:100}]);
  context.syncTintControls({tint_color:'#FF20A0',tint_strength:100});
  elements.aeTintStrength.value=45;elements.aeTintStrength.oninput();await flush();
  assert.strictEqual(calls.pop()[1].tint_strength,45);
  await elements.aeTintReset.onclick();await Promise.resolve();
  assert.strictEqual(calls.pop()[1].tint_strength,0);
  assert(elements.aeTintValue.textContent.includes('原色'));
  response={ok:false,json:async()=>({error:'颜色未应用'})};
  elements.aeTintColor.value='#00ff00';await elements.aeTintColor.onchange();await Promise.resolve();
  assert(elements.message.textContent.includes('颜色未应用'));
  // A delayed failed request must not erase a more recent colour selection.
  const waiting=[];
  context.post=(path,values)=>new Promise(resolve=>waiting.push({values:JSON.parse(JSON.stringify(values)),resolve}));
  elements.aeTintColor.value='#00c8ff';const first=elements.aeTintColor.onchange();
  elements.aeTintColor.value='#ff2080';elements.aeTintColor.oninput();await flush();
  assert.strictEqual(waiting.length,1);
  waiting[0].resolve({ok:false,json:async()=>({error:'earlier failed'})});await first;
  assert.strictEqual(waiting.length,2);assert.strictEqual(waiting[1].values.tint_color,'#ff2080');
  waiting[1].resolve({ok:true});await new Promise(resolve=>setImmediate(resolve));
  console.log('AE_LIVE_TINT_INPUT_AND_STALE_REFRESH_OK');
})().catch(error=>{console.error(error);process.exitCode=1;});
