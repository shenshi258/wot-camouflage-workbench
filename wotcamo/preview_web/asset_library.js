// Shared by the standalone library and the model-painting drawer. User names
// are rendered as text; neither names nor categories become paths or HTML.
export class AssetLibrary{
 constructor(root,{base=new URL('./',location.href),onUse=null,onClose=null,isBusy=()=>false}={}){
  this.root=root;this.base=base;this.onUse=onUse;this.onClose=onClose;this.isBusy=isBusy;
  this.items=[];this.selected=null;this.busy=false;this.removed=null;this.revision=0;this.useRevision=0;
  root.classList.add('asset-library');
  root.innerHTML=`<div class="asset-toolbar"><div class="asset-heading"><strong>图片素材库</strong><button data-lib="close" type="button" aria-label="关闭素材库">关闭</button></div>
   <div class="asset-actions"><button data-lib="import" class="asset-primary" type="button">导入图片…</button><button data-lib="folder" type="button">导入文件夹…</button><button data-lib="refresh" type="button">刷新</button></div>
   <input data-lib="files" type="file" accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" multiple hidden>
   <input data-lib="directory" type="file" webkitdirectory multiple hidden>
   <label class="asset-category-import">导入分类 <input data-lib="importCategory" maxlength="40" value="未分类" aria-label="导入分类"></label></div>
   <div class="asset-filters"><input data-lib="search" placeholder="搜索名称或分类" aria-label="搜索素材"><select data-lib="category" aria-label="筛选分类"><option value="">全部分类</option></select></div>
   <div data-lib="status" class="asset-status" role="status" aria-live="polite">图片保存在程序目录的“素材库/图片元素”，再次打开仍可使用。</div>
   <div data-lib="grid" class="asset-grid" aria-label="素材缩略图"></div>
   <div data-lib="chosen" class="asset-selected" hidden><div class="asset-chosen"><img data-lib="chosenImage" class="asset-chosen-image" alt="选中素材"><div class="asset-chosen-meta"><strong data-lib="chosenName"></strong><small data-lib="chosenSize"></small></div><button data-lib="use" class="asset-primary" type="button"></button></div>
   <details class="asset-edit"><summary>编辑名称 / 分类</summary><label>名称 <input data-lib="name" maxlength="100" aria-label="素材名称"></label><label>分类 <input data-lib="editCategory" maxlength="40" aria-label="素材分类"></label><div class="asset-actions"><button data-lib="save" type="button">保存修改</button><button data-lib="remove" type="button">移出素材库</button></div></details></div>
   <div class="asset-actions" style="padding:0 10px 8px"><button data-lib="undo" type="button" hidden>撤销移出</button></div>
   <dialog data-lib="preview"><button data-lib="previewClose" type="button">关闭预览</button><img data-lib="largeImage" alt="素材大图"></dialog>`;
  this.el('close').hidden=!onClose;this.el('close').onclick=()=>onClose?.();
  this.el('use').textContent=onUse?'使用素材':'放大预览';
  this.el('import').onclick=()=>this.el('files').click();this.el('folder').onclick=()=>this.el('directory').click();
  for(const key of ['files','directory'])this.el(key).onchange=()=>{const files=Array.from(this.el(key).files);this.el(key).value='';this.importFiles(files);};
  this.el('refresh').onclick=()=>this.load().catch(error=>this.error(error));
  for(const key of ['search','category'])this.el(key).addEventListener(key==='search'?'input':'change',()=>this.renderGrid());
  this.el('use').onclick=()=>this.use();this.el('save').onclick=()=>this.edit();this.el('remove').onclick=()=>this.remove();this.el('undo').onclick=()=>this.restore();
  this.el('previewClose').onclick=()=>this.el('preview').close();
  const help={import:'多选 PNG / JPG / WebP，每批最多 128 张；保存副本，原图保留。',folder:'导入文件夹及子文件夹内的图片，每批最多 128 张。',refresh:'读取其他窗口新增或修改的素材。',importCategory:'新素材使用此分类；重复文件保留库内已有分类。',search:'按名称或分类筛选，不修改已放置到车身的图案。',category:'只筛选显示；修改分类请展开下方编辑区域。',name:'显示名称，最多 100 个字符；不改原始文件名。',editCategory:'分类最多 40 个字符，留空为未分类。',save:'保存名称和分类，不改图片内容。',remove:'移到图库回收站，保留原图和已经放置的图案。',undo:'撤销本窗口最近一次移出；回收副本仍保留在库目录。',use:onUse?'载入为当前贴图；保存当前贴图后可以继续添加。':'放大查看素材及透明边缘。',previewClose:'关闭大图预览，返回素材库。'};
  for(const [key,text] of Object.entries(help))this.el(key).title=text;
 }
 el(name){return this.root.querySelector(`[data-lib="${name}"]`);}
 url(path){return new URL(path,this.base).href;}
 message(text){this.el('status').textContent=text;}
 error(error){this.message('操作未完成：'+(error instanceof TypeError?'连接已断开，请重新打开素材库。':(error.message||String(error))));}
 async api(path,data){
  const response=await fetch(this.url(path),data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  let result;try{result=await response.json();}catch{throw Error('素材库连接异常，请重新打开。');}
  if(!response.ok)throw Error(result.error||'素材操作失败。');return result;
 }
 async load(select=this.selected?.id){
  const revision=++this.revision,result=await this.api('library/list');if(revision!==this.revision)return;
  this.items=result.items;const current=this.el('category').value;this.el('category').replaceChildren(new Option('全部分类',''));
  for(const category of Array.from(new Set(this.items.map(item=>item.category))).sort((a,b)=>a.localeCompare(b,'zh')))this.el('category').add(new Option(category,category));
  this.el('category').value=Array.from(this.el('category').options).some(option=>option.value===current)?current:'';
  this.renderGrid();this.select(this.items.find(item=>item.id===select)||null);
  this.message(`共 ${this.items.length} 项 · 单张最多 8 MB · PNG / JPG / WebP`+(result.issues?`；${result.issues} 项记录无法读取。`:''));
 }
 renderGrid(){
  const query=this.el('search').value.trim().toLocaleLowerCase(),category=this.el('category').value;
  const visible=this.items.filter(item=>(!category||item.category===category)&&(!query||`${item.name} ${item.category}`.toLocaleLowerCase().includes(query)));
  const grid=this.el('grid');grid.replaceChildren();
  for(const item of visible){
   const button=document.createElement('button');button.type='button';button.className='asset-tile';button.dataset.assetId=item.id;
   button.title=`${item.name}\n${item.category} · ${item.width}×${item.height}`;button.setAttribute('aria-pressed',String(this.selected?.id===item.id));
   const image=document.createElement('img');image.src=this.url('library/thumb/'+item.id);image.loading='lazy';image.alt='';
   const text=document.createElement('span');text.textContent=item.name;button.append(image,text);
   button.onclick=()=>this.select(item);button.ondblclick=()=>{this.select(item);this.use();};button.disabled=this.busy;grid.append(button);
  }
  if(!visible.length){const empty=document.createElement('div');empty.className='asset-empty';empty.textContent=this.items.length?'没有匹配的素材，请调整名称或分类筛选。':'还没有图片素材。可自行批量导入标志、文字、线条等图片，透明 PNG 可保留透明背景。';grid.append(empty);}
 }
 select(item){
  this.selected=item;this.el('chosen').hidden=!item;
  for(const button of this.el('grid').querySelectorAll('[data-asset-id]'))button.setAttribute('aria-pressed',String(button.dataset.assetId===item?.id));
  if(item){
   this.el('chosenImage').src=this.url('library/thumb/'+item.id);this.el('chosenName').textContent=item.name;
   this.el('chosenName').title=item.name;
   this.el('chosenSize').textContent=`${item.width}×${item.height} · ${item.category}`;
   this.el('chosenSize').title=this.el('chosenSize').textContent;
   this.el('name').value=item.name;this.el('editCategory').value=item.category;
  }
  this.updateButtons();
 }
 updateButtons(){
  this.root.setAttribute('aria-busy',String(this.busy));
  for(const key of ['import','folder','refresh','files','directory','importCategory','name','editCategory','save','remove','undo'])this.el(key).disabled=this.busy;
  this.el('use').disabled=this.busy||!this.selected||this.isBusy();this.el('undo').hidden=!this.removed;
  for(const button of this.el('grid').querySelectorAll('button'))button.disabled=this.busy;
 }
 async importFiles(files){
  if(this.busy||!files.length)return;
  const supported=files.filter(file=>/\.(png|jpe?g|webp)$/i.test(file.name));
  if(!supported.length){this.message('请选择 PNG、JPG 或 WebP 图片；动画可用 AE 的 GIF / 视频导入。');return;}
  if(supported.length>128){this.message('单次最多导入 128 张图片，请分批选择。');return;}
  this.busy=true;this.updateButtons();let added=0,duplicates=0,last=null;const errors=[];
  try{
   for(const [index,file] of supported.entries()){
    this.message(`正在导入 ${index+1} / ${supported.length}：${file.name}`);
    try{
     if(file.size>8*1024*1024)throw Error('超过 8 MB');
     const image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('文件读取失败'));reader.readAsDataURL(file);});
     const result=await this.api('library/import',{name:file.name,category:this.el('importCategory').value||'未分类',image});
     if(result.duplicate)duplicates++;else added++;last=result.item.id;
    }catch(error){errors.push(file.name+'：'+(error.message||String(error)));}
   }
   this.el('search').value='';this.el('category').value='';await this.load(last);
   this.message(`导入完成：新增 ${added}，重复 ${duplicates}，失败 ${errors.length}`+(files.length>supported.length?`，跳过非图片 ${files.length-supported.length} 项`:'')+(errors.length?'。'+errors.slice(0,2).join('；'):''));
  }catch(error){this.error(error);}finally{this.busy=false;this.updateButtons();}
 }
 async use(){
  const item=this.selected;if(!item||this.busy)return;
  if(this.isBusy()){this.message('正在生成涂装，请完成后再使用素材。');return;}
  // 资源读取有先后差异；只让最后一次“使用素材”的响应进入贴图流程。
  const revision=++this.useRevision;
  try{
   if(this.onUse){
    const response=await fetch(this.url('library/image/'+item.id));if(!response.ok)throw Error('图片读取失败，可先移出该项后重新导入。');
    const blob=await response.blob();if(revision!==this.useRevision)return;
    const used=await this.onUse(blob,item);if(used!==false&&revision===this.useRevision)this.message('已载入“'+item.name+'”，点击模型放置；保存当前贴图后可继续添加。');
   }else{this.el('largeImage').src=this.url('library/image/'+item.id);this.el('largeImage').alt=item.name;this.el('preview').showModal();}
  }catch(error){if(revision===this.useRevision)this.error(error);}
 }
 async edit(){
  if(!this.selected||this.busy)return;this.busy=true;this.updateButtons();
  try{const result=await this.api('library/action',{action:'edit',id:this.selected.id,name:this.el('name').value,category:this.el('editCategory').value});await this.load(result.item.id);this.message('名称和分类已保存。');}
  catch(error){this.error(error);}finally{this.busy=false;this.updateButtons();}
 }
 async remove(){
  if(!this.selected||this.busy)return;this.busy=true;this.updateButtons();
  try{const result=await this.api('library/action',{action:'remove',id:this.selected.id});this.removed=result.trash_id;this.selected=null;await this.load();this.message('已移出素材库，可撤销移出；副本保留在素材库的“回收站”，原始图片保留。');}
  catch(error){this.error(error);}finally{this.busy=false;this.updateButtons();}
 }
 async restore(){
  if(!this.removed||this.busy)return;this.busy=true;this.updateButtons();
  try{const result=await this.api('library/action',{action:'restore',trash_id:this.removed});this.removed=null;await this.load(result.item.id);this.message('素材已恢复。');}
  catch(error){this.error(error);}finally{this.busy=false;this.updateButtons();}
 }
}
