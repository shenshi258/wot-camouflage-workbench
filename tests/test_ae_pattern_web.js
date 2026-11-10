// Execute the actual preview handlers with fetch-style boolean response.ok.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const code = fs.readFileSync(process.argv[2], 'utf8');
const begin = code.indexOf("$('aeFitMode').onchange="), end = code.indexOf("$('aeResetWarp').onclick=", begin);
assert(begin >= 0 && end > begin);
const elements = Object.fromEntries(['aeFitMode','aeCopySettings','aePasteSettings','message'].map(id => [id, {value:'tile',textContent:''}]));
const calls = [];
let response = {ok:true}, networkError = false;
const context = {$: id => elements[id], effectInfo:{config:{fit_mode:'contain'}}, post: async (route, data) => {
  calls.push([route, JSON.parse(JSON.stringify(data))]);
  if (networkError) throw Error('offline');
  return response;
}};
vm.createContext(context);
vm.runInContext(code.slice(begin, end), context);
(async () => {
  await elements.aeCopySettings.onclick();
  assert.deepStrictEqual(calls.pop(), ['effectsettings',{action:'copy'}]);
  assert(elements.message.textContent.includes('复制'));
  await elements.aePasteSettings.onclick();
  assert.deepStrictEqual(calls.pop(), ['effectsettings',{action:'paste'}]);
  assert(elements.message.textContent.includes('粘贴'));
  await elements.aeFitMode.onchange();
  assert.deepStrictEqual(calls.pop(), ['effectparams',{fit_mode:'tile'}]);
  response = {ok:false};
  await elements.aePasteSettings.onclick();
  assert(elements.message.textContent.includes('未完成'));
  await elements.aeFitMode.onchange();
  assert.strictEqual(elements.aeFitMode.value, 'contain');
  networkError = true;
  await elements.aeCopySettings.onclick();
  assert(elements.message.textContent.includes('未完成'));
  await elements.aeFitMode.onchange();
  assert(elements.message.textContent.includes('未应用'));
  console.log('AE_COPY_PASTE_AND_FIT_HANDLERS_OK');
})().catch(error => {console.error(error); process.exitCode = 1;});
