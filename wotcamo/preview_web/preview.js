import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';

const $=id=>document.getElementById(id), base=new URL('./',location.href);
const paintMode=new URLSearchParams(location.search).get('paint')==='1';
// Help is presentation-only: these descriptions never alter renderer/export
// parameters. Keep the same units and action names as the desktop authoring UI.
const controlHelp={fit:'恢复整车居中视角，不清除特效或选区。',part:'只筛选预览部件，不会改变生成内容。',quality:'调整预览速度与清晰度，不改变输出资源。',bloom:'显示近似泛光；游戏内曝光仍需实测。',bright:'切换明亮背景，便于检查透明边缘。',wire:'显示网格线，帮助核对选面范围。',yaw:'只调整预览中的炮塔角度。',pitch:'只调整预览中的炮管俯仰。',play:'暂停或继续预览动画。',restart:'从第一帧重新播放，不重置位置。',aePick:'点选单个面或相连平面，完成后点击使用选区。Shift 加选，Ctrl 减选。',aeAdjust:'整体与横纵倍率可以分别调整。松开滑块后应用；四边裁剪不会拉伸剩余图像。',paintScale:'贴图大小相对于原贴图宽度的比例，按图片原始宽高比缩放。',paintAngle:'旋转当前贴图，单位度。',paintClear:'清除当前尚未保存的图片，不清除已保存的贴图。'};
for(const [id,text] of Object.entries(controlHelp)){const element=$(id);if(element)element.title=text;}
for(const field of document.querySelectorAll('[data-ae-param]'))field.title=field.dataset.aeParam.startsWith('crop_')?'从原动画对应边裁掉的百分比；相对两边合计须小于 100%。':'贴面素材大小倍率，1 为原大小；横纵调整彼此独立。';
if(paintMode)$('operationHelpText').textContent='点击模型表面，再导入图片，调整大小和角度。保存当前贴图后可以继续添加；最后点击生成涂装包。共用 UV 的位置会一起变化。';
const url=path=>new URL(path,base).href;
const errors=[];let fatal=null,ready=false,bodyInfo=null,lampInfo=null,applied=-1,loadingLamps=false;
let paused=false,elapsed=0,lastTime=performance.now(),lastRender=0,dirty=true,picked=[],selectionTexture=null;
let animationTexture=null,parameterTexture=null,animationWidth=128,animationHeight=1,animationKey=null;
let bodyRoot=null,lampRoot=null,parts={},geometryKey=null,visiblePart='all';
const textures=new Map(),lampMaterials=new Set(),raycaster=new THREE.Raycaster();
const stats={fps:0,calls:0,triangles:0,scale:1,gpu:'',frames:0};
window.addEventListener('error',event=>{errors.push(event.message);$('message').textContent='渲染错误：'+event.message;});
window.addEventListener('unhandledrejection',event=>{errors.push(String(event.reason));$('message').textContent='资源加载失败：'+event.reason;});
let renderer,composer,bloom,camera,scene,controls,ground,grid;
let effectInfo=null,effectRoot=null,effectMeshes=[],effectFrame=-1,placingEffect=false,pickingEffect=false,snappingEffect=false;
try{
 renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,powerPreference:'high-performance'});
 renderer.setPixelRatio(1);renderer.outputColorSpace=THREE.SRGBColorSpace;
 renderer.info.autoReset=false;
 renderer.debug.onShaderError=(gl,program,vertex,fragment)=>{
  fatal='预览着色器编译失败：'+gl.getProgramInfoLog(program)+' '+gl.getShaderInfoLog(vertex)+' '+gl.getShaderInfoLog(fragment);
  errors.push(fatal);$('message').textContent=fatal;
 };
 renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;
 $('viewport').appendChild(renderer.domElement);
 const gl=renderer.getContext(),extension=gl.getExtension('WEBGL_debug_renderer_info');
 stats.gpu=extension?gl.getParameter(extension.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
 scene=new THREE.Scene();scene.background=new THREE.Color('#0b111c');
 camera=new THREE.PerspectiveCamera(40,1,.03,500);camera.position.set(10,7,12);
 controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,2,0);controls.maxPolarAngle=Math.PI*.93;
 controls.addEventListener('change',()=>{dirty=true;});
 scene.add(new THREE.HemisphereLight(0xd5e7ff,0x283042,2.1));
 const sun=new THREE.DirectionalLight(0xfff3dd,2.6);sun.position.set(-6,12,8);scene.add(sun);
 const fill=new THREE.DirectionalLight(0x91b9ff,1.25);fill.position.set(6,4,-8);scene.add(fill);
 ground=new THREE.Mesh(new THREE.PlaneGeometry(100,100),new THREE.MeshStandardMaterial({color:0x111d2b,roughness:1}));
 ground.rotation.x=-Math.PI/2;ground.position.y=-.02;scene.add(ground);
 grid=new THREE.GridHelper(40,40,0x38516b,0x203247);grid.position.y=-.01;scene.add(grid);
 composer=new EffectComposer(renderer);composer.addPass(new RenderPass(scene,camera));
 bloom=new UnrealBloomPass(new THREE.Vector2(800,600),.65,.35,1.15);composer.addPass(bloom);composer.addPass(new OutputPass());
 renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();fatal='显卡渲染上下文已丢失，请关闭并重新打开三维预览。';$('message').textContent=fatal;});
 renderer.domElement.addEventListener('webglcontextrestored',()=>location.reload());
}catch(error){fatal=String(error);$('message').textContent='无法创建三维渲染窗口，请检查显卡驱动与硬件加速：'+fatal;}

const vertexShader=`attribute float lampBand;attribute float faceId;varying vec2 vUv;varying float vBand;varying float vFace;
void main(){vUv=uv;vBand=lampBand;vFace=faceId;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`;
const fragmentShader=`uniform sampler2D emission;uniform sampler2D animation;uniform sampler2D parameters;uniform sampler2D selectedFaces;
uniform float seconds;uniform float lutWidth;uniform float lutHeight;uniform float faceCount;uniform bool animated;uniform bool hasMap;
varying vec2 vUv;varying float vBand;varying float vFace;
void main(){vec4 tex=hasMap?texture2D(emission,vUv):vec4(1.0);vec3 color=tex.rgb;float alpha=tex.a;
 if(animated&&vBand>=0.0){float row=(floor(vBand+0.5)+0.5)/lutHeight;vec4 param=texture2D(parameters,vec2(0.25,row));
 float t=mod(seconds,max(param.x,0.001))/max(param.x,0.001)*(lutWidth-1.0);float lo=floor(t);
 vec4 a=texture2D(animation,vec2((lo+0.5)/lutWidth,row));vec4 b=texture2D(animation,vec2((min(lo+1.0,lutWidth-1.0)+0.5)/lutWidth,row));
 color*=mix(a.rgb,b.rgb,fract(t))*texture2D(parameters,vec2(0.75,row)).x;
 if(param.w>0.5){float pulse=0.5*(1.0+cos(6.28318530718*seconds/max(param.y,0.001)));color*=param.z+(1.0-param.z)*pulse;}}
 float picked=texture2D(selectedFaces,vec2((floor(vFace+0.5)+0.5)/faceCount,0.5)).r;
 color+=picked*vec3(0.12,0.3,0.5);gl_FragColor=vec4(color,alpha);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;

async function json(path){const response=await fetch(url(path));if(!response.ok)throw Error(path+' '+response.status);return response.json();}
async function binary(path){const response=await fetch(url(path));if(!response.ok)throw Error(path+' '+response.status);return response.arrayBuffer();}
function image(path,linear=false){
 if(!path)return null;
 if(!textures.has(path)){
  const texture=new THREE.TextureLoader().load(url(path),()=>{dirty=true;},undefined,()=>errors.push('贴图加载失败：'+path));
  texture.colorSpace=linear?THREE.NoColorSpace:THREE.SRGBColorSpace;texture.flipY=false;
  texture.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy());textures.set(path,texture);
 }
 return textures.get(path);
}
async function loadMesh(data,path,isLamp){
 const [vb,ib]=await Promise.all([binary(path+data.vertex),binary(path+data.index)]);
 const vertices=new Float32Array(vb),geometry=new THREE.BufferGeometry();
 const buffer=new THREE.InterleavedBuffer(vertices,data.stride);
 geometry.setAttribute('position',new THREE.InterleavedBufferAttribute(buffer,3,0));
 geometry.setAttribute('normal',new THREE.InterleavedBufferAttribute(buffer,3,3));
 geometry.setAttribute('uv',new THREE.InterleavedBufferAttribute(buffer,2,6));
 geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(ib),1));
 let material;
 if(isLamp){
  geometry.setAttribute('faceId',new THREE.InterleavedBufferAttribute(buffer,1,8));
  geometry.setAttribute('lampBand',new THREE.InterleavedBufferAttribute(buffer,1,9));
  const map=image(data.texture?path+data.texture:null,data.kind==='lamp');
  material=new THREE.ShaderMaterial({vertexShader,fragmentShader,side:THREE.DoubleSide,transparent:true,depthTest:true,depthWrite:false,
    blending:THREE.CustomBlending,blendSrc:THREE.SrcColorFactor,blendDst:THREE.OneMinusSrcAlphaFactor,
    uniforms:{emission:{value:map},animation:{value:animationTexture},parameters:{value:parameterTexture},
     selectedFaces:{value:selectionTexture},seconds:{value:elapsed},lutWidth:{value:animationWidth},lutHeight:{value:animationHeight},
     faceCount:{value:Math.max(1,lampInfo?.faceIds?.length||1)},animated:{value:data.kind==='lamp'},hasMap:{value:!!map}}});
  lampMaterials.add(material);
 }else{
  const map=image(data.texture?path+data.texture:null);
  // Glow planes need blending; drawing them opaque hides the model beneath.
  // The source's common destination factors 3 and 6 mirror the lamp preview.
  // UML volumetric effects use a custom shader, so approximate with its alpha
  // map and additive blending instead of rendering solid opaque triangles.
  material=data.volume?new THREE.MeshBasicMaterial({map,color:0xffffff,side:THREE.DoubleSide,
    transparent:true,depthWrite:false,blending:THREE.AdditiveBlending}):data.emissive?new THREE.MeshBasicMaterial({map,color:map?0xffffff:0x72a5dd,side:THREE.DoubleSide,
    transparent:true,depthWrite:false,blending:THREE.CustomBlending,blendSrc:THREE.SrcColorFactor,
    blendDst:data.glowDestBlend==='3'?THREE.SrcColorFactor:THREE.OneMinusSrcAlphaFactor}):
   new THREE.MeshStandardMaterial({map,color:map?0xffffff:0x8795a4,roughness:.72,metalness:.18,side:THREE.DoubleSide,alphaTest:data.alphaTest||0});
 }
 material.wireframe=$('wire').checked;
 geometry.computeBoundingBox();geometry.computeBoundingSphere();
 const object=new THREE.Mesh(geometry,material);object.userData={part:data.part,kind:data.kind,meshIndex:data.meshIndex};return object;
}
function groupParts(root,offsets){
 const chassis=new THREE.Group(),hull=new THREE.Group(),turret=new THREE.Group(),gun=new THREE.Group(),gunStatic=new THREE.Group();
 chassis.name='chassis';hull.name='hull';turret.name='turret';gun.name='gun';
 gunStatic.name='gunStatic';root.add(chassis,hull);hull.add(turret);turret.add(gun,gunStatic);
 hull.position.fromArray(offsets.hull);turret.position.fromArray(offsets.turret);gun.position.fromArray(offsets.gun);
 gunStatic.position.fromArray(offsets.gun);
 turret.rotation.y=THREE.MathUtils.degToRad(Number($('yaw').value));gun.rotation.x=THREE.MathUtils.degToRad(-Number($('pitch').value));
 return {chassis,hull,turret,gun,gunStatic};
}
function disposeGroup(root){
 if(!root)return;
 const maps=new Set();root.traverse(object=>{if(!object.isMesh)return;object.geometry.dispose();
  const material=object.material;
  if(material.map)maps.add(material.map);
  if(material.uniforms?.emission?.value)maps.add(material.uniforms.emission.value);
  lampMaterials.delete(material);material.dispose();});
 scene.remove(root);
 for(const map of maps){map.dispose();for(const [key,value] of textures)if(value===map)textures.delete(key);}
}
function updateSelection(ids){
 picked=ids||[];
 if(!lampInfo)return;
 const width=Math.max(1,lampInfo.faceIds.length),data=new Float32Array(width*4);
 const set=new Set(picked);lampInfo.faceIds.forEach((id,i)=>{data[i*4]=set.has(id)?1:0;data[i*4+3]=1;});
 if(selectionTexture)selectionTexture.dispose();
 selectionTexture=new THREE.DataTexture(data,width,1,THREE.RGBAFormat,THREE.FloatType);selectionTexture.needsUpdate=true;
 for(const material of lampMaterials){material.uniforms.selectedFaces.value=selectionTexture;material.uniforms.faceCount.value=width;}
 dirty=true;
}
async function loadBody(info){
 bodyInfo=info;const root=new THREE.Group();root.scale.x=-1;
 $('pitch').disabled=info.pitchSupported===false;
 if(info.pitchSupported===false){$('pitch').value=0;$('pitch').title='该车含混合关节网格，暂仅显示原始炮管姿态';}
 const groups=groupParts(root,info.offsets);
 const objects=await Promise.all(info.meshes.map((data,meshIndex)=>loadMesh({...data,meshIndex},'body/',false)));
 objects.forEach((object,i)=>groups[info.meshes[i].part==='gun'&&info.meshes[i].inclined===false?'gunStatic':info.meshes[i].part].add(object));
 disposeGroup(bodyRoot);bodyRoot=root;parts=groups;scene.add(root);
 $('vehicle').textContent=info.vehicle;updateWarnings();fit();
}
function effectMeshArrays(info,index){
 const reflected=info.config.placement==='plane'&&index>0;
 const positions=info.vertices.flatMap(v=>[reflected?-v[0]:v[0],v[1],v[2]]);
 const indices=reflected?Array.from({length:info.indices.length/3},(_,i)=>[info.indices[i*3],info.indices[i*3+2],info.indices[i*3+1]]).flat():info.indices;
 return {positions,indices};
}
function loadEffect(info){
 disposeGroup(effectRoot);effectMeshes=[];effectInfo=info;effectFrame=-1;
 const root=new THREE.Group();root.scale.x=-1;const groups=groupParts(root,bodyInfo.offsets);
 const map=image('effect/atlas.png?v='+info.atlas_sha256,true);
 map.generateMipmaps=false;map.minFilter=THREE.LinearFilter;map.magFilter=THREE.LinearFilter;map.anisotropy=1;
 const material=new THREE.ShaderMaterial({side:THREE.DoubleSide,transparent:true,depthTest:true,depthWrite:false,
  blending:THREE.CustomBlending,blendSrc:THREE.SrcAlphaFactor,blendDst:info.blendDst===2?THREE.OneFactor:THREE.OneMinusSrcAlphaFactor,
  uniforms:{emission:{value:map},gain:{value:info.config.brightness}},
  vertexShader:'varying vec2 texUV;void main(){texUV=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
  fragmentShader:'varying vec2 texUV;uniform sampler2D emission;uniform float gain;void main(){vec4 p=texture2D(emission,texUV);gl_FragColor=vec4(p.rgb*gain,p.a);}'
 });
 info.positions.forEach((position,index)=>{
  const shape=effectMeshArrays(info,index);
  const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(shape.positions,3));
  geo.setAttribute('uv',new THREE.Float32BufferAttribute(info.vertices.flatMap(v=>v.slice(6,8)),2));geo.setIndex(shape.indices);geo.computeBoundingSphere();
  const object=new THREE.Mesh(geo,material);object.position.fromArray(position);object.userData={kind:'ae',part:info.part};
  groups[info.part].add(object);effectMeshes.push(object);
 });effectRoot=root;scene.add(root);buildHandles(info);
 $('aeColorTools').hidden=false;$('aeTintColor').value=info.config.tint_color||'#FFFFFF';$('aeTintStrength').value=info.config.tint_strength||0;$('aeTintValue').textContent=Number($('aeTintStrength').value).toFixed(0)+'%';$('aeMirror').checked=!!info.config.mirror;$('aeTools').hidden=false;$('selectionTools').hidden=false;$('modeTitle').textContent='AE 特效 · 三维预览';
 $('aeAppearanceTools').hidden=false;
 for(const input of document.querySelectorAll('[data-ae-appearance]')){
  if(document.activeElement!==input)input.value=info.config[input.dataset.aeAppearance]??(input.dataset.aeAppearance==='transparency'?0:1);
  showAppearanceValue(input);
 }
 $('operationHelpText').textContent='独立平面：拖动任一侧发光面可移动，拖原侧四角或边控制点可同步变形；Shift 拖动沿法线移入移出。双侧平面需放在车体一侧，横向位置为 0 时会重合。贴面可点“吸附装甲”或点选/框选后“使用选区”。套用预设时贴面保留当前映射方向。生成涂装 ZIP 会附带本次特效预设。';
 $('aePlace').hidden=info.config.placement!=='plane';$('aeResetWarp').hidden=info.config.placement!=='plane';
 if($('aeDrag')){$('aeDrag').hidden=info.config.placement!=='plane';$('aeDrag').textContent='拖动变形：'+(deformEnabled?'开':'关');}
 for(const field of document.querySelectorAll('[data-ae-param]')){
  const key=field.dataset.aeParam;field.value=info.config[key]??(key.startsWith('crop_')?0:1);
  field.disabled=info.config.placement==='plane'&&key==='uv_scale';showEffectValue(field);
 }
 if(info.awaiting_selection&&!snappingEffect){snappingEffect=true;$('aeSnap').textContent='请点击装甲表面…';}
 $('hint').textContent='左键旋转 · 右键平移 · 滚轮缩放 · 拖动发光面移动或拉角变形（Shift 沿法线）';
 updateVisibility();dirty=true;
}
let deformEnabled=true,effectDrag=null,handleGroup=null,handleMeshes=[],dragPlane=new THREE.Plane();
const handleGeometry=new THREE.OctahedronGeometry(1,0);
function buildHandles(info){
 effectDrag=null;handleGroup=null;handleMeshes=[];
 if(!info||info.config.placement!=='plane'||!effectMeshes.length||!info.corners||!info.corners.length)return;
 const group=new THREE.Group(),cornerMat=new THREE.MeshBasicMaterial({color:0x8fd0ff,transparent:true,opacity:.95,depthTest:false,depthWrite:false}),edgeMat=new THREE.MeshBasicMaterial({color:0x9bb7d9,transparent:true,opacity:.8,depthTest:false,depthWrite:false}),moveMat=new THREE.MeshBasicMaterial({color:0xffcf7a,transparent:true,opacity:.85,depthTest:false,depthWrite:false});
 const corners=info.corners.map(c=>new THREE.Vector3().fromArray(c));
 const add=(position,material,kind,index)=>{const mesh=new THREE.Mesh(handleGeometry,material);mesh.position.copy(position);mesh.renderOrder=20;mesh.userData={kind:'aeHandle',part:info.part,handle:kind,index};group.add(mesh);handleMeshes.push(mesh);return mesh;};
 corners.forEach((p,i)=>add(p,cornerMat,'corner',i));
 [[0,1],[1,2],[2,3],[3,0]].forEach((edges,i)=>add(corners[edges[0]].clone().add(corners[edges[1]]).multiplyScalar(.5),edgeMat,'edge',i));
 add(corners.reduce((sum,p)=>sum.add(p),new THREE.Vector3()).multiplyScalar(.25),moveMat,'move',0);
 effectMeshes[0].add(group);handleGroup=group;group.visible=deformEnabled;
}
function updateHandleScale(){
 if(!handleGroup)return;
 const distance=camera.position.distanceTo(handleGroup.getWorldPosition(new THREE.Vector3()));
 const pixels=Math.max(1,renderer.domElement.clientHeight||1),worldPerPixel=2*distance*Math.tan(THREE.MathUtils.degToRad(camera.fov*.5))/pixels;
 for(const mesh of handleMeshes)mesh.scale.setScalar(Math.max(1e-4,worldPerPixel*7));
}
function screenPoint(object){const rect=renderer.domElement.getBoundingClientRect(),p=object.getWorldPosition(new THREE.Vector3()).project(camera);return {x:rect.left+(p.x+1)*rect.width/2,y:rect.top+(1-p.y)*rect.height/2,visible:p.z<1};}
function pickHandle(x,y){
 let found=null,best=15;
 for(const mesh of handleMeshes){if(!mesh.visible)continue;const p=screenPoint(mesh);if(!p.visible)continue;const distance=Math.hypot(p.x-x,p.y-y);if(distance<=best){best=distance;found=mesh;}}
 return found;
}
function planeRayHit(x,y,point){
 const rect=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((x-rect.left)/rect.width*2-1,-(y-rect.top)/rect.height*2+1),camera);
 dragPlane.setFromNormalAndCoplanarPoint(camera.getWorldDirection(new THREE.Vector3()).negate(),point);
 const hit=new THREE.Vector3();return raycaster.ray.intersectPlane(dragPlane,hit)?hit:null;
}
function localDeltaFromWorld(mesh,from,to){
 const matrix=new THREE.Matrix3().setFromMatrix4(mesh.matrixWorld).invert();
 return to.clone().sub(from).applyMatrix3(matrix);
}
function planeAxes(delta,config){
 // Convert a geometry-space delta into the plane's own horizontal/vertical axes.
 const xx=config.plane==='front'?delta.x:config.plane==='top'?delta.x:-delta.z;
 const yy=config.plane==='front'?delta.y:config.plane==='top'?-delta.z:delta.y;
 const angle=THREE.MathUtils.degToRad(config.angle),cs=Math.cos(angle),sn=Math.sin(angle);
 return {horizontal:cs*xx+sn*yy,vertical:-sn*xx+cs*yy};
}
function applyDraggedCorners(corners){
 const weights=(effectInfo&&effectInfo.weights)||[];
 // Both preview meshes own a geometry buffer; update each during the drag.
 for(const [index,mesh] of effectMeshes.entries()){
  const array=mesh.geometry.attributes.position.array;
  for(let i=0;i<weights.length;i++){
   const w=weights[i];
   const x=w[0]*corners[0].x+w[1]*corners[1].x+w[2]*corners[2].x+w[3]*corners[3].x;
   array[i*3]=(effectInfo.config.placement==='plane'&&index>0)?-x:x;
   array[i*3+1]=w[0]*corners[0].y+w[1]*corners[1].y+w[2]*corners[2].y+w[3]*corners[3].y;
   array[i*3+2]=w[0]*corners[0].z+w[1]*corners[1].z+w[2]*corners[2].z+w[3]*corners[3].z;
  }
  mesh.geometry.attributes.position.needsUpdate=true;mesh.geometry.computeBoundingSphere();
 }
 for(const handle of handleMeshes){
  if(handle.userData.handle==='corner')handle.position.copy(corners[handle.userData.index]);
  else if(handle.userData.handle==='edge'){
   const pair=[[0,1],[1,2],[2,3],[3,0]][handle.userData.index];
   handle.position.copy(corners[pair[0]]).add(corners[pair[1]]).multiplyScalar(.5);
  }else handle.position.copy(corners.reduce((sum,p)=>sum.add(p),new THREE.Vector3()).multiplyScalar(.25));
 }
 dirty=true;
}
function startEffectDrag(event,handle,pickedMesh=null){
 if(!effectInfo||!effectMeshes.length)return false;
 const mesh=handle?effectMeshes[0]:(pickedMesh||effectMeshes[0]);
 const anchor=handle?handle.getWorldPosition(new THREE.Vector3()):mesh.getWorldPosition(new THREE.Vector3());
 const startPoint=planeRayHit(event.clientX,event.clientY,anchor);
 if(!startPoint)return false;
 effectDrag={handle:handle?handle.userData.handle:'move',index:handle?handle.userData.index:0,startPoint,mesh,pickedIndex:Math.max(0,effectMeshes.indexOf(mesh)),
  startPositions:effectMeshes.map(x=>x.position.clone()),
  startCorners:((effectInfo.corners||[]).map(c=>new THREE.Vector3().fromArray(c))),
  startConfig:{...effectInfo.config},startY:event.clientY,
  worldPerPixel:2*camera.position.distanceTo(anchor)*Math.tan(THREE.MathUtils.degToRad(camera.fov*.5))/Math.max(1,renderer.domElement.clientHeight)};
 controls.enabled=false;try{renderer.domElement.setPointerCapture(event.pointerId);}catch(error){}
 $('message').textContent='拖动中：松开鼠标应用。';
 return true;
}
function moveEffectDrag(event){
 if(!effectDrag)return;
 const point=planeRayHit(event.clientX,event.clientY,effectDrag.startPoint);
 if(!point)return;
 const delta=localDeltaFromWorld(effectDrag.mesh,effectDrag.startPoint,point);
 const config=effectDrag.startConfig,axis=config.plane==='front'?'z':config.plane==='top'?'y':'x';
 // Camera-plane deltas have no depth when facing the surface straight on.
 // Screen distance makes Shift-depth work from that view as well.
 if(event.shiftKey){const amount=(effectDrag.startY-event.clientY)*effectDrag.worldPerPixel;delta.set(0,0,0);delta[axis]=amount;}
 else if(effectDrag.handle!=='move')delta[axis]=0;
 if(effectDrag.handle==='move'){
  // The second position is -x: invert only its lateral motion before
  // updating the primary position so the grabbed side follows the cursor.
  if(effectDrag.pickedIndex>0)delta.x=-delta.x;
  effectMeshes.forEach((mesh,index)=>{
   const base=effectDrag.startPositions[index],mirrored=effectDrag.startPositions.length>1&&index>0;
   mesh.position.set(base.x+(mirrored?-delta.x:delta.x),base.y+delta.y,base.z+delta.z);
  });
 }else{
  const corners=effectDrag.startCorners.map(c=>c.clone());
  const affected=effectDrag.handle==='corner'?[effectDrag.index]:[[0,1],[1,2],[2,3],[3,0]][effectDrag.index];
  for(const index of affected)corners[index].add(delta);
  applyDraggedCorners(corners);
 }
 dirty=true;
}
async function finishEffectDrag(commit){
 const drag=effectDrag;effectDrag=null;controls.enabled=true;
 if(!drag)return;
 if(!commit){loadEffect(effectInfo);return;}
 const config=drag.startConfig,values={},round=x=>Number(x.toFixed(5)),clamp=(value,low,high)=>Math.min(high,Math.max(low,value));
 if(drag.handle==='move'){
  const base=drag.startPositions[0],moved=effectMeshes[0].position;
  values.x=round(clamp(config.x+moved.x-base.x,-30,30));values.y=round(clamp(config.y+moved.y-base.y,-30,30));values.z=round(clamp(config.z+moved.z-base.z,-30,30));
 }else{
  const cornerHandles=handleMeshes.filter(handle=>handle.userData.handle==='corner').sort((a,b)=>a.userData.index-b.userData.index);
  const halfW=Math.max(1e-6,(effectInfo.base_size?.[0]||1)/2),halfH=Math.max(1e-6,(effectInfo.base_size?.[1]||1)/2);
  const affected=drag.handle==='corner'?[drag.index]:[[0,1],[1,2],[2,3],[3,0]][drag.index];
  for(const index of affected){
   const delta=cornerHandles[index].position.clone().sub(drag.startCorners[index]);
   const axes=planeAxes(delta,config),corner=['tl','tr','br','bl'][index];
   values['warp_'+corner+'_x']=round(clamp(config['warp_'+corner+'_x']+axes.horizontal/halfW,-2,2));
   values['warp_'+corner+'_y']=round(clamp(config['warp_'+corner+'_y']+axes.vertical/halfH,-2,2));
   const axis=config.plane==='front'?'z':config.plane==='top'?'y':'x';
   values['warp_'+corner+'_z']=round(clamp(config['warp_'+corner+'_z']+delta[axis]/Math.min(halfW,halfH),-2,2));
  }
 }
 try{const response=await post('effectparams',values);if(!response.ok){const problem=await response.json();throw Error(problem.error||'拖动结果无法应用');}$('message').textContent='位置与变形已更新。';}
 catch(error){$('message').textContent=String(error);loadEffect(effectInfo);}
}
function animateEffect(){
 if(!effectInfo)return;
 const index=Math.min(effectInfo.frames-1,Math.floor((elapsed%effectInfo.period)*effectInfo.fps));
 if(index===effectFrame)return;effectFrame=index;
 const r=effectInfo.rects[index],uv=effectInfo.local_uv.flatMap(v=>[r[0]+v[0]*(r[2]-r[0]),r[1]+v[1]*(r[3]-r[1])]);
 for(const object of effectMeshes){object.geometry.attributes.uv.array.set(uv);object.geometry.attributes.uv.needsUpdate=true;}
 $('aeFrame').textContent=`第 ${index+1} / ${effectInfo.frames} 帧 · ${effectInfo.fps} FPS`;
}
function placeEffect(x,y){
 const rect=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((x-rect.left)/rect.width*2-1,-(y-rect.top)/rect.height*2+1),camera);
 const hit=raycaster.intersectObject(bodyRoot,true).find(h=>h.object.visible&&['hull','turret','gun'].includes(h.object.userData.part));
 if(!hit)return;
 const part=hit.object.userData.part,group=bodyRoot.getObjectByName(part);
 const world=hit.point.clone(),normal=hit.face.normal.clone().transformDirection(hit.object.matrixWorld);world.addScaledVector(normal,.025);
 const position=group.worldToLocal(world).toArray();post('effectplace',{part,position});placingEffect=false;$('aePlace').textContent='点击模型放置';
}
$('aePlace').onclick=()=>{placingEffect=!placingEffect;pickingEffect=false;snappingEffect=false;areaMode=false;$('aeSnap').textContent='吸附装甲';$('aePick').textContent='点选承载面：关';$('aePlace').textContent=placingEffect?'请点击承载表面…':'点击模型放置';};
$('aePick').onclick=()=>{pickingEffect=!pickingEffect;placingEffect=false;snappingEffect=false;areaMode=false;$('aeSnap').textContent='吸附装甲';$('box').textContent='框选车体：关';$('aePick').textContent='点选承载面：'+(pickingEffect?'开':'关');};
$('aeSnap').onclick=()=>{snappingEffect=!snappingEffect;placingEffect=false;pickingEffect=false;areaMode=false;$('aePick').textContent='点选承载面：关';$('box').textContent='框选车体：关';$('aeSnap').textContent=snappingEffect?'请点击装甲表面…':'吸附装甲';};
function showEffectValue(field){field.nextElementSibling.textContent=Number(field.value).toFixed(field.dataset.aeParam.startsWith('crop_')?0:2)+(field.dataset.aeParam.startsWith('crop_')?'%':'×');}
$('aeNewPlane').onclick=async()=>{placingEffect=false;pickingEffect=false;snappingEffect=false;areaMode=false;$('aeSnap').textContent='吸附装甲';$('aePick').textContent='点选承载面：关';$('box').textContent='框选车体：关';const response=await post('effectplane',{});if(!response.ok)$('message').textContent='未能创建平面，请返回编辑窗口重试。';};
$('aeResetWarp').onclick=async()=>{const values=Object.fromEntries(Object.keys(effectInfo.config).filter(k=>k.startsWith('warp_')).map(k=>[k,0]));await post('effectparams',values);};
for(const field of document.querySelectorAll('[data-ae-param]')){
 field.oninput=()=>showEffectValue(field);
 field.onchange=async()=>{
  try{const values=Object.fromEntries(Array.from(document.querySelectorAll('[data-ae-param]'),input=>[input.dataset.aeParam,Number(input.value)]));const response=await post('effectparams',values);if(!response.ok){const problem=await response.json();throw Error(problem.error||'参数无法应用');}$('message').textContent='正在更新缩放与裁剪…';}
  catch(error){$('message').textContent=String(error);field.value=effectInfo.config[field.dataset.aeParam];showEffectValue(field);}
 };
}
function planarFaces(object,first){
 // Connectivity is local to one authenticated preview mesh. Coincident edge
 // coordinates bridge UV seams; bends and separate panels stop the flood fill.
 const geo=object.geometry,index=geo.index,pos=geo.attributes.position;
 if(!object.userData.aeConnectivity){
  const edges=new Map(),triangles=[];const point=i=>new THREE.Vector3().fromBufferAttribute(pos,i);
  const key=p=>[p.x,p.y,p.z].map(x=>Math.round(x*10000)).join(',');
  for(let i=0;i<index.count/3;i++){
   const p=[0,1,2].map(j=>point(index.getX(i*3+j))),keys=p.map(key),n=p[1].clone().sub(p[0]).cross(p[2].clone().sub(p[0])).normalize();
   triangles.push({p:p[0],n,edges:[]});
   for(let j=0;j<3;j++){const e=[keys[j],keys[(j+1)%3]].sort().join('|');if(!edges.has(e))edges.set(e,[]);edges.get(e).push(i);triangles[i].edges.push(e);}
  }object.userData.aeConnectivity={edges,triangles};
 }
 const {edges,triangles}=object.userData.aeConnectivity,base=triangles[first],chosen=new Set([first]),queue=[first];
 while(queue.length&&chosen.size<=5000){for(const edge of triangles[queue.pop()].edges)for(const other of edges.get(edge)){
  const t=triangles[other];if(!chosen.has(other)&&Math.abs(t.n.dot(base.n))>.998&&Math.abs(t.p.clone().sub(base.p).dot(base.n))<.002){chosen.add(other);queue.push(other);}
 }}return chosen;
}
function pickEffectFace(x,y,event={}){
 if(!bodyRoot)return null;
 const rect=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((x-rect.left)/rect.width*2-1,-(y-rect.top)/rect.height*2+1),camera);
 const hit=raycaster.intersectObject(bodyRoot,true).find(h=>h.object.visible&&h.object.userData.kind==='body');if(!hit)return null;
 const mesh=hit.object.userData.meshIndex,faces=$('aePickKind').value==='planar'?planarFaces(hit.object,hit.faceIndex):new Set([hit.faceIndex]);
 if(!event.shiftKey&&!event.ctrlKey&&!event.metaKey)areaFaces.clear();const selected=areaFaces.get(mesh)||new Set();
 for(const i of faces){if(event.ctrlKey||event.metaKey)selected.delete(i);else selected.add(i);}
 if(selected.size)areaFaces.set(mesh,selected);else areaFaces.delete(mesh);refreshArea();
 const count=Array.from(areaFaces.values()).reduce((n,s)=>n+s.size,0);$('aePick').textContent='点选承载面：开 · '+count+' 面';return {mesh,triangle:hit.faceIndex,count};
}
function armorSurfaceFaces(hit){
 // A material boundary is not an armour boundary. Collect coplanar faces
 // across meshes in the same posed part, but never jump to the opposite side,
 // another moving joint, an existing glow plane or an unrelated angled plate.
 const groups=new Map(),point=hit.object.worldToLocal(hit.point.clone()),normal=hit.face.normal.clone().normalize();
 let count=0;const seen=new Set();
 bodyRoot.traverse(object=>{
  if(!object.isMesh||!object.visible||object.parent!==hit.object.parent||object.userData.kind!=='body')return;
  const entry=bodyInfo.meshes[object.userData.meshIndex];if(entry?.emissive||entry?.volume)return;
  const index=object.geometry.index,pos=object.geometry.attributes.position,selected=new Set();
  for(let i=0;i<index.count;i+=3){
   const vertices=[0,1,2].map(j=>new THREE.Vector3().fromBufferAttribute(pos,index.getX(i+j)));
   const n=vertices[1].clone().sub(vertices[0]).cross(vertices[2].clone().sub(vertices[0]));
   if(n.lengthSq()<1e-18||Math.abs(n.normalize().dot(normal))<.995||vertices.some(p=>Math.abs(p.clone().sub(point).dot(normal))>.012))continue;
   const key=vertices.map(p=>[p.x,p.y,p.z].map(x=>Math.round(x*10000)).join(',')).sort().join('|');
   if(seen.has(key))continue;seen.add(key);selected.add(i/3);count++;
  }
  if(selected.size)groups.set(object.userData.meshIndex,selected);
 });return {groups,count};
}
async function snapEffect(x,y){
 if(!bodyRoot)return null;
 const rect=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((x-rect.left)/rect.width*2-1,-(y-rect.top)/rect.height*2+1),camera);
 const hit=raycaster.intersectObject(bodyRoot,true).find(h=>h.object.visible&&h.object.userData.kind==='body'&&['hull','turret','gun'].includes(h.object.userData.part)&&!bodyInfo.meshes[h.object.userData.meshIndex]?.emissive&&!bodyInfo.meshes[h.object.userData.meshIndex]?.volume);
 if(!hit){$('message').textContent='请点击车体、炮塔或炮管的装甲表面。';return null;}
 const mesh=hit.object.userData.meshIndex;
 const surface=$('aeWholeArmor').checked?armorSurfaceFaces(hit):{groups:new Map([[mesh,planarFaces(hit.object,hit.faceIndex)]])};
 const count=Array.from(surface.groups.values()).reduce((n,faces)=>n+faces.size,0);
 if(!count||count>5000){$('message').textContent='装甲范围为空或超过 5000 面，请取消整块装甲后点选，或框选较小区域。';return null;}
 // Inverse the entire posed object transform, including root reflection and
 // turret/gun rotation. The server authenticates these original face IDs and
 // the exporter checks that this bind-space point remains inside the selection.
 const point=hit.object.worldToLocal(hit.point.clone()).toArray();
 try{
  const response=await post('bodyselect',{batches:Array.from(surface.groups,([mesh,faces])=>({mesh,triangles:Array.from(faces)})),snap:true,point});
  if(!response.ok){const problem=await response.json();throw Error(problem.error||'装甲选区校验失败');}
  areaFaces.clear();for(const [mesh,faces] of surface.groups)areaFaces.set(mesh,faces);refreshArea();snappingEffect=false;$('aeSnap').textContent='吸附装甲';$('message').textContent='已吸附 '+count+' 面；可分别调整长度和宽度。';
  return {mesh,triangle:hit.faceIndex,count,point};
 }catch(error){$('message').textContent=String(error);return null;}
}
async function loadLamps(info,revision){
 loadingLamps=true;
 try{
  let animation=animationTexture;
  if(info.animationKey!==animationKey||!animation){
   const animationData=new Float32Array(await binary('lamps/'+(info.animationRevision??revision)+'/animation.bin'));
   animation=new THREE.DataTexture(animationData,info.lutWidth,info.lutHeight,THREE.RGBAFormat,THREE.FloatType);animation.needsUpdate=true;
  }
  const params=new Float32Array(info.lutHeight*8);
  info.tracks.forEach((track,i)=>params.set([track.period,track.breath,track.low,track.nativePulse?1:0,track.gain??1,0,0,0],i*8));
  const parameters=new THREE.DataTexture(params,2,info.lutHeight,THREE.RGBAFormat,THREE.FloatType);parameters.needsUpdate=true;
  const oldAnimation=animationTexture,oldParameters=parameterTexture;
  animationTexture=animation;parameterTexture=parameters;animationWidth=info.lutWidth;animationHeight=info.lutHeight;
  lampInfo=info;updateSelection(picked);
  const nextKey=info.geometryKey||String(revision);
  if(nextKey!==geometryKey){
   const root=new THREE.Group();root.scale.x=-1;const groups=groupParts(root,bodyInfo.offsets);
   const path='lamps/'+(info.meshRevision??revision)+'/';
   const objects=await Promise.all(info.meshes.map(data=>loadMesh(data,path,true)));
   objects.forEach((object,i)=>groups[info.meshes[i].part].add(object));
   disposeGroup(lampRoot);lampRoot=root;scene.add(root);geometryKey=nextKey;
  }
  for(const material of lampMaterials){Object.assign(material.uniforms.animation,{value:animationTexture});
   material.uniforms.parameters.value=parameterTexture;material.uniforms.lutWidth.value=animationWidth;material.uniforms.lutHeight.value=animationHeight;}
  if(oldAnimation&&oldAnimation!==animationTexture)oldAnimation.dispose();if(oldParameters)oldParameters.dispose();animationKey=info.animationKey;
  applied=revision;ready=true;updateVisibility();updateWarnings();dirty=true;
 }finally{loadingLamps=false;}
}
function updateWarnings(){if(!bodyInfo)return;$('warnings').textContent=[...(bodyInfo.warnings||[]),...(lampInfo?.warnings||[])].join('\n');}
function fit(){
 if(!bodyRoot)return;
 const box=new THREE.Box3().setFromObject(bodyRoot),center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());
 const radius=Math.max(size.length()/2,1);controls.target.copy(center);
 camera.position.copy(center).add(new THREE.Vector3(radius*1.15,radius*.65,radius*1.4));
 camera.near=Math.max(.015,radius/1000);camera.far=Math.max(300,radius*40);camera.updateProjectionMatrix();
 controls.minDistance=.2;controls.maxDistance=radius*15;controls.update();
 ground.position.y=box.min.y-.03;grid.position.y=box.min.y-.02;dirty=true;
}
function updateVisibility(){
 for(const root of [bodyRoot,lampRoot,effectRoot])if(root)root.traverse(object=>{if(object.isMesh&&object.userData.kind!=='aeHandle')object.visible=visiblePart==='all'||object.userData.part===visiblePart;});
 if(handleGroup)handleGroup.visible=deformEnabled&&(visiblePart==='all'||visiblePart===effectInfo?.part);
 dirty=true;
}
function setPose(){
 for(const root of [bodyRoot,lampRoot,effectRoot])if(root){root.getObjectByName('turret').rotation.y=THREE.MathUtils.degToRad(Number($('yaw').value));root.getObjectByName('gun').rotation.x=THREE.MathUtils.degToRad(-Number($('pitch').value));}
 $('yawValue').textContent=$('yaw').value+'°';$('pitchValue').textContent=$('pitch').value+'°';dirty=true;
}
function resize(){
 if(!renderer)return;const box=$('viewport').getBoundingClientRect();
 const quality=$('quality').value;
 const ratio=(quality==='fast'?.7:quality==='fine'?Math.min(1.5,Math.max(1.25,devicePixelRatio)):Math.min(devicePixelRatio,1))*stats.scale;
 renderer.setPixelRatio(ratio);renderer.setSize(box.width,box.height,false);composer.setPixelRatio(ratio);composer.setSize(box.width,box.height);
 camera.aspect=box.width/Math.max(1,box.height);camera.updateProjectionMatrix();bloom.enabled=$('bloom').checked&&quality!=='fast';$('bloom').disabled=quality==='fast';dirty=true;
}
async function poll(){
 if(fatal)return;
 try{
  const status=await json('status');window.applyWorkbenchTheme?.(status.uiTheme);picked=status.state.picked||[];
  if(paintMode&&!poll.paintNameReady){$('paintName').value=status.paintTitle||'我的涂装';poll.paintNameReady=true;}
  if(status.closed){if(window.pywebview?.api)window.pywebview.api.close();return;}
  if(status.state.performance&&status.state.performance!==poll.lastPerformance){
   poll.lastPerformance=status.state.performance;$('quality').value=status.state.performance;stats.scale=1;resize();
  }
  if(status.body&&!bodyRoot)await loadBody(status.body);
  if(status.effect&&bodyRoot&&!effectDrag&&status.effect.revision!==effectInfo?.revision){loadEffect(status.effect);setPose();}
  if(status.ready&&bodyRoot&&!loadingLamps&&status.readyRevision>applied)await loadLamps(status.ready,status.readyRevision);
  const currentPicked=JSON.stringify(picked);
  if(currentPicked!==poll.lastPicked){poll.lastPicked=currentPicked;updateSelection(picked);}
  if(status.error)$('message').textContent='预览未更新：'+status.error.message;
  else if(applied<status.state.revision)$('message').textContent=status.progress.message+'（保留上次有效画面）';
  else $('message').textContent=effectInfo?.awaiting_selection?'点选或框选承载面，再点击“使用选区”。':paintMode||effectInfo?'':(lampInfo?.tracks.length?'':'请在制作器中勾选灯面，再查看动态灯效。');
 }catch(error){$('message').textContent='正在连接制作器… '+error.message;}
 setTimeout(poll,250);
}
function post(path,value){return fetch(url(path),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});}
function pickAt(x,y,event={}){
 if(!lampRoot||!lampInfo)return null;
 const rect=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((x-rect.left)/rect.width*2-1,-(y-rect.top)/rect.height*2+1),camera);
 const hits=raycaster.intersectObject(lampRoot,true).filter(hit=>hit.object.visible);
 if(!hits.length)return null;
 const hit=hits[0],attribute=hit.object.geometry.getAttribute('faceId');const index=Math.round(attribute.getX(hit.face.a));
 if(bodyRoot){const bodyHit=raycaster.intersectObject(bodyRoot,true).find(hit=>hit.object.visible);
  if(bodyHit&&bodyHit.distance<hit.distance-.0001)return null;}
 const id=lampInfo.faceIds[index];
 if(id)post('select',{id,add:!!event.shiftKey,subtract:!!(event.ctrlKey||event.metaKey)});
 return id;
}
let areaMode=false,areaStart=null,areaFaces=new Map(),areaOverlays=[];
let paintImage=null,paintBase64=null,paintHit=null,paintCanvas=null,paintTexture=null,paintChanged=[];
const paintLayers=[];let paintTextures=[],paintBusy=false,paintFileRevision=0;
function resetPaint(){
 for(const [object,map] of paintChanged)object.material.map=map;
 paintChanged=[];for(const map of paintTextures)map.dispose();paintTextures=[];paintTexture=null;paintCanvas=null;dirty=true;
}
function currentPaint(){return paintHit&&paintImage&&paintBase64?{...paintHit,image:paintBase64,bitmap:paintImage,scale:Number($('paintScale').value),angle:Number($('paintAngle').value)}:null;}
function paintPayload(layer){return {mesh:layer.mesh,u:layer.u,v:layer.v,scale:layer.scale,angle:layer.angle,image:layer.image};}
function paintCounter(){$('paintCount').textContent='已保存 '+paintLayers.length+' 张';$('paintUndo').disabled=!paintLayers.length||paintBusy;}
// Rebuild each texture from its untouched base and the ordered saved layers.
// Slider changes affect only the current draft; saved images stay fixed.
function updatePaint(){
 resetPaint();
 if(!bodyInfo)return;
 const draft=currentPaint(),all=draft?[...paintLayers,draft]:paintLayers,groups=new Map();
 for(const layer of all){const key=bodyInfo.meshes[layer.mesh].texture;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(layer);}
 for(const [key,layers] of groups){
 const first=layers[0],baseImage=first.map?.image;
 const width=baseImage?.naturalWidth||baseImage?.width, height=baseImage?.naturalHeight||baseImage?.height;
 if(!width||!height){$('paintStatus').textContent='原贴图仍在加载，请稍后点击模型。';continue;}
 const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
 const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(baseImage,0,0,width,height);
 const basePixels=ctx.getImageData(0,0,width,height);
 for(const layer of layers){
 const w=width*layer.scale,h=w*layer.bitmap.naturalHeight/layer.bitmap.naturalWidth;
 ctx.save();ctx.translate(layer.u*width,layer.v*height);ctx.rotate(layer.angle*Math.PI/180);
 ctx.drawImage(layer.bitmap,-w/2,-h/2,w,h);ctx.restore();
 const pixels=ctx.getImageData(0,0,width,height);
 for(let i=3;i<pixels.data.length;i+=4)pixels.data[i]=basePixels.data[i];
 ctx.putImageData(pixels,0,0);
 }
 const map=new THREE.CanvasTexture(canvas);map.flipY=false;
 map.colorSpace=THREE.SRGBColorSpace;map.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy());paintTextures.push(map);
 if(draft&&bodyInfo.meshes[draft.mesh].texture===key){paintCanvas=canvas;paintTexture=map;}
 // A texture can be shared by several meshes; updating all of them makes
 // overlapping UVs visible before the user creates the game package.
 bodyRoot.traverse(object=>{
  if(!object.isMesh||object.userData.kind!=='body')return;
  const data=bodyInfo.meshes[object.userData.meshIndex];
  if(data.texture===key){paintChanged.push([object,object.material.map]);object.material.map=map;object.material.needsUpdate=true;}
 });
 }
 if(draft&&paintCanvas){const width=paintCanvas.width,height=paintCanvas.height;
 const alpha=paintCanvas.getContext('2d').getImageData(Math.min(width-1,Math.floor(draft.u*width)),Math.min(height-1,Math.floor(draft.v*height)),1,1).data[3];
 $('paintStatus').textContent=alpha===0?'点击位置的原贴图透明；若图片不可见，请点其他位置。':'已实时预览；共用该贴图和 UV 的其他位置也会变化。';dirty=true;
 }paintCounter();
}
function clearCurrentPaint(){paintFileRevision++;paintImage=paintBase64=paintHit=null;$('paintFile').value='';updatePaint();}
function saveCurrentPaint(){
 if(paintBusy)return;
 const layer=currentPaint();if(!layer||!paintCanvas){$('paintStatus').textContent='请先导入图片，在模型上放好位置再保存。';return;}
 if(paintLayers.length>=32){$('paintStatus').textContent='最多保存 32 张，请先生成涂装包。';return;}
 if(paintLayers.reduce((sum,x)=>sum+x.image.length,layer.image.length)>Math.ceil(32*1024*1024*4/3)){$('paintStatus').textContent='图片总大小不能超过 32 MB。';return;}
 paintLayers.push(layer);clearCurrentPaint();$('paintStatus').textContent='当前贴图已保存，可继续添加下一张；关闭前请生成涂装包。';
}
function paintPick(x,y){
 if(paintBusy)return;
 if(!bodyRoot||!bodyInfo)return;
 const rect=renderer.domElement.getBoundingClientRect();
 raycaster.setFromCamera(new THREE.Vector2((x-rect.left)/rect.width*2-1,-(y-rect.top)/rect.height*2+1),camera);
 const hit=raycaster.intersectObject(bodyRoot,true).find(h=>h.object.visible&&h.object.userData.kind==='body');
 if(!hit||!hit.uv){$('paintStatus').textContent='没有点到可编辑的模型表面。';return;}
 const index=hit.object.userData.meshIndex,entry=bodyInfo.meshes[index],texture=(entry.source?.texture||'').replaceAll('\\','/').toLowerCase();
 if(!entry.texture||!texture.endsWith('_am.dds')||hit.uv.x<0||hit.uv.x>1||hit.uv.y<0||hit.uv.y>1){
  $('paintStatus').textContent='该位置没有可编辑的 AM 贴图或 UV 超出范围，请点击其他部位。';return;
 }
 const oldMap=paintChanged.find(pair=>pair[0]===hit.object)?.[1]||hit.object.material.map;
 paintHit={mesh:index,u:hit.uv.x,v:hit.uv.y,map:oldMap};
 if(!paintImage){$('paintStatus').textContent='已选择模型位置，请导入图片。';return;}
 updatePaint();
}
function setupPaint(){
 if(!paintMode)return;
 $('paintTools').hidden=false;document.title='wot涂装工作台 3.3 · 三维模型贴图';$('modeTitle').textContent='三维模型贴图';
 $('selectionTools').hidden=true;$('playbackTools').hidden=true;
 $('hint').textContent='拖动旋转 · 右键平移 · 滚轮缩放 · 点击放置图片';
 $('paintFile').onchange=()=>{
  const file=$('paintFile').files[0];if(!file)return;
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)){$('paintStatus').textContent='请选择 PNG、JPG 或 WebP 图片。';return;}
  if(file.size>8*1024*1024){$('paintStatus').textContent='图片不能超过 8 MB。';return;}
 const revision=++paintFileRevision,reader=new FileReader();reader.onerror=()=>{$('paintStatus').textContent='图片读取失败。';};
  reader.onload=()=>{const data=String(reader.result),image=new Image();image.onload=()=>{
   if(revision!==paintFileRevision)return;
   if(image.naturalWidth*image.naturalHeight>25000000){$('paintStatus').textContent='图片超过 2500 万像素。';return;}
   paintImage=image;paintBase64=data.split(',')[1];$('paintStatus').textContent='图片已载入，请点击模型表面。';updatePaint();
  };image.onerror=()=>{$('paintStatus').textContent='图片格式不支持。';};image.src=data;};reader.readAsDataURL(file);
 };
 $('paintScale').oninput=()=>{$('paintScaleValue').textContent=Math.round(Number($('paintScale').value)*100)+'%';updatePaint();};
 $('paintAngle').oninput=()=>{$('paintAngleValue').textContent=$('paintAngle').value+'°';updatePaint();};
 $('paintSave').onclick=saveCurrentPaint;
 window.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();if(!e.repeat)saveCurrentPaint();}});
 $('paintUndo').onclick=()=>{if(paintBusy)return;paintLayers.pop();updatePaint();$('paintStatus').textContent='已撤销上一张保存的贴图。';};
 $('paintClear').onclick=()=>{clearCurrentPaint();$('paintStatus').textContent='已清除当前图片，已保存的贴图仍保留。';};
 $('paintExport').onclick=async()=>{
  const draft=currentPaint(),layers=draft?[...paintLayers,draft]:[...paintLayers];
  if(!layers.length){$('paintStatus').textContent='请先选择图片并点击模型放置。';return;}
  if(layers.length>32){$('paintStatus').textContent='最多导出 32 张图片，请先清除当前图片或撤销上一张。';return;}
  const btn=$('paintExport');btn.disabled=true;$('paintStatus').textContent='正在生成并检查贴图，请稍候…';
  paintBusy=true;for(const id of ['paintSave','paintUndo','paintClear','paintFile','paintScale','paintAngle'])$(id).disabled=true;
  try{const response=await post('paint',{title:$('paintName').value,layers:layers.map(paintPayload)});
   const data=await response.json();if(!response.ok)throw Error(data.error||'生成失败');
   $('paintStatus').textContent='待测包已生成：'+data.path;
  }catch(e){$('paintStatus').textContent='生成失败：'+String(e.message||e);}finally{paintBusy=false;btn.disabled=false;for(const id of ['paintSave','paintClear','paintFile','paintScale','paintAngle'])$(id).disabled=false;paintCounter();}
 };
}

function refreshArea(){
 for(const overlay of areaOverlays){overlay.parent.remove(overlay);overlay.geometry.dispose();overlay.material.dispose();}
 areaOverlays=[];
 if(!bodyRoot)return;
 bodyRoot.traverse(object=>{
  if(!object.isMesh||object.userData.kind!=='body')return;
  const selected=areaFaces.get(object.userData.meshIndex);if(!selected||!selected.size)return;
  const indices=object.geometry.getIndex(),data=[];
  for(const tri of selected)for(let k=0;k<3;k++)data.push(indices.getX(tri*3+k));
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',object.geometry.getAttribute('position'));geometry.setIndex(data);
  const overlay=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color:0x00ddff,transparent:true,opacity:.55,side:THREE.DoubleSide,depthTest:true,depthWrite:false,polygonOffset:true,polygonOffsetFactor:-2,polygonOffsetUnits:-2}));
  overlay.userData={kind:'areaOverlay',part:object.userData.part};object.add(overlay);areaOverlays.push(overlay);
 });dirty=true;
}
function rectangleFaces(start,end,evt){
 if(!bodyRoot)return;const box=renderer.domElement.getBoundingClientRect();
 const x0=Math.min(start[0],end[0]),x1=Math.max(start[0],end[0]),y0=Math.min(start[1],end[1]),y1=Math.max(start[1],end[1]);
 if(!evt.shiftKey&&!evt.ctrlKey&&!evt.metaKey)areaFaces.clear();
 scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);
 const position=new THREE.Vector3(),center=new THREE.Vector3();let count=0;
 bodyRoot.traverse(object=>{
  if(!object.isMesh||object.userData.kind!=='body'||!object.visible)return;
  const index=object.geometry.getIndex(),pos=object.geometry.getAttribute('position');
  let selected=areaFaces.get(object.userData.meshIndex)||new Set();
  for(let i=0;i<index.count/3;i++){
   center.set(0,0,0);for(let k=0;k<3;k++){position.fromBufferAttribute(pos,index.getX(i*3+k));center.add(position);}center.multiplyScalar(1/3).applyMatrix4(object.matrixWorld).project(camera);
   if(center.z < -1 || center.z > 1)continue;
   const x=box.left+(center.x+1)*box.width/2,y=box.top+(1-center.y)*box.height/2;
   if(x>=x0&&x<=x1&&y>=y0&&y<=y1){if(evt.ctrlKey||evt.metaKey)selected.delete(i);else selected.add(i);}
  }
  if(selected.size)areaFaces.set(object.userData.meshIndex,selected);else areaFaces.delete(object.userData.meshIndex);
 });
 for(const set of areaFaces.values())count+=set.size;
 $('box').textContent='框选车体：开 · '+count+' 面';refreshArea();
}
let down=null;
function canDragEffect(){return deformEnabled&&!!effectInfo&&effectInfo.config.placement==='plane'&&(visiblePart==='all'||visiblePart===effectInfo.part)&&!areaMode&&!snappingEffect&&!pickingEffect&&!placingEffect&&!paintMode&&!!effectMeshes.length;}
function pickEffectSurface(x,y){
 const rect=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((x-rect.left)/rect.width*2-1,-(y-rect.top)/rect.height*2+1),camera);
 return raycaster.intersectObjects(effectMeshes,false).find(hit=>hit.object.visible)||null;
}
if(renderer){
 renderer.domElement.addEventListener('pointerdown',e=>{if(e.button!==0)return;if(canDragEffect()){const handle=pickHandle(e.clientX,e.clientY);if(handle&&startEffectDrag(e,handle)){e.stopImmediatePropagation();return;}const hit=!handle&&pickEffectSurface(e.clientX,e.clientY);if(hit&&startEffectDrag(e,null,hit.object)){e.stopImmediatePropagation();return;}}if(areaMode){areaStart=[e.clientX,e.clientY];controls.enabled=false;renderer.domElement.setPointerCapture(e.pointerId);e.stopImmediatePropagation();}else down=[e.clientX,e.clientY];},true);
 renderer.domElement.addEventListener('pointermove',e=>{if(effectDrag){moveEffectDrag(e);e.stopImmediatePropagation();return;}if(!areaStart)return;const bounds=$('viewport').getBoundingClientRect(),r=$('selectionRect');r.style.display='block';r.style.left=(Math.min(areaStart[0],e.clientX)-bounds.left)+'px';r.style.top=(Math.min(areaStart[1],e.clientY)-bounds.top)+'px';r.style.width=Math.abs(areaStart[0]-e.clientX)+'px';r.style.height=Math.abs(areaStart[1]-e.clientY)+'px';e.stopImmediatePropagation();},true);
 renderer.domElement.addEventListener('pointerup',e=>{if(effectDrag){finishEffectDrag(true);e.stopImmediatePropagation();down=null;return;}if(areaStart){rectangleFaces(areaStart,[e.clientX,e.clientY],e);areaStart=null;controls.enabled=true;$('selectionRect').style.display='none';e.stopImmediatePropagation();}else if(down&&Math.hypot(e.clientX-down[0],e.clientY-down[1])<4){if(snappingEffect&&effectInfo)snapEffect(e.clientX,e.clientY);else if(pickingEffect&&effectInfo)pickEffectFace(e.clientX,e.clientY,e);else if(placingEffect&&effectInfo)placeEffect(e.clientX,e.clientY);else if(paintMode)paintPick(e.clientX,e.clientY);else pickAt(e.clientX,e.clientY,e);}down=null;},true);
 renderer.domElement.addEventListener('pointercancel',()=>{if(effectDrag)finishEffectDrag(false);areaStart=null;controls.enabled=true;$('selectionRect').style.display='none';});
 $('box').onclick=()=>{areaMode=!areaMode;pickingEffect=false;placingEffect=false;snappingEffect=false;$('aeSnap').textContent='吸附装甲';controls.enabled=true;$('box').textContent='框选车体：'+(areaMode?'开':'关');};
 const dragToggle=$('aeDrag');if(dragToggle)dragToggle.onclick=()=>{deformEnabled=!deformEnabled;dragToggle.textContent='拖动变形：'+(deformEnabled?'开':'关');if(handleGroup)handleGroup.visible=deformEnabled;dirty=true;};
 $('clearArea').onclick=()=>{areaFaces.clear();refreshArea();$('box').textContent='框选车体：'+(areaMode?'开':'关');};
 $('applyArea').onclick=async()=>{const batches=Array.from(areaFaces,([mesh,triangles])=>({mesh,triangles:Array.from(triangles)}));if(!batches.length){alert('请先框选车体区域。');return;}const count=batches.reduce((a,b)=>a+b.triangles.length,0);if(count>(effectInfo?5000:20000)){alert('选区过大，请缩小选区（AE 最多 5000 面）。');return;}try{const response=await post('bodyselect',{batches});if(!response.ok)throw Error('选区校验失败 '+response.status);if(effectInfo){$('message').textContent='承载选区已更新，保留当前呈现和透明设置；需要贴面时请在编辑窗口切换呈现方式。';}else alert('选区已发送到制作器，请在主窗口选择下一步。');}catch(e){alert(String(e));}};
 new ResizeObserver(resize).observe($('viewport'));
 $('fit').onclick=fit;$('restart').onclick=()=>{elapsed=0;dirty=true;};
 $('play').onclick=()=>{paused=!paused;$('play').textContent=paused?'播放':'暂停';dirty=true;};
 $('part').onchange=()=>{visiblePart=$('part').value;updateVisibility();};
 $('quality').onchange=()=>{stats.scale=1;resize();post('performance',{value:$('quality').value});};$('bloom').onchange=resize;
 $('bright').onchange=()=>{const bright=$('bright').checked;scene.background.set(bright?'#d7e1ed':'#0b111c');ground.material.color.set(bright?'#bccbd9':'#111d2b');dirty=true;};
 $('wire').onchange=()=>{for(const root of [bodyRoot,lampRoot])if(root)root.traverse(o=>{if(o.isMesh)o.material.wireframe=$('wire').checked;});dirty=true;};
 $('yaw').oninput=$('pitch').oninput=setPose;
}
let statStart=performance.now(),count=0,adaptiveStart=performance.now();
function render(){
 animateEffect();
 updateHandleScale();
 renderer.info.reset();
 for(const material of lampMaterials)material.uniforms.seconds.value=elapsed;
 if(bloom.enabled||effectInfo)composer.render();else renderer.render(scene,camera);
 stats.calls=renderer.info.render.calls;stats.triangles=renderer.info.render.triangles;stats.frames++;count++;dirty=false;
}
function tick(now){
 requestAnimationFrame(tick);
 const delta=Math.min((now-lastTime)/1000,.15);lastTime=now;
 if(document.hidden||fatal)return;
 if(!paused)elapsed+=delta;
 const interval=$('quality').value==='fast'?1000/30:1000/60;
 if(now-lastRender>=interval-.5&&(dirty||(!paused&&(lampInfo?.tracks.length||effectInfo)))){render();lastRender=now-((now-lastRender)%interval);}
 if(now-statStart>=1000){
  stats.fps=count*1000/(now-statStart);count=0;statStart=now;
  $('stats').textContent=`${paused?'已暂停':(paintMode&&!lampInfo?.tracks.length?'按需刷新':stats.fps.toFixed(0)+' FPS')} · ${$('quality').selectedOptions[0].text.split(' · ')[0]}\n绘制 ${stats.calls} · 三角面 ${stats.triangles.toLocaleString()}\n渲染比例 ${(renderer.getPixelRatio()*100).toFixed(0)}%`;
 }
 if(now-adaptiveStart>5000&&ready&&!paused){
  if($('quality').value==='balanced'&&stats.fps<38&&stats.fps>0&&stats.scale>.6){stats.scale=Math.max(.6,stats.scale-.1);resize();}
  post('metrics',{...stats,ready,revision:applied,performance:$('quality').value,bodyTriangles:bodyInfo?.triangles||0});adaptiveStart=now;
 }
}
window.previewTest={
 newPlaneTest:()=>{$('aeNewPlane').click();return true;},
 sizeAdjustTest:()=>{
  $('aeScaleX').value=2;$('aeScaleY').value=.5;$('aeScaleX').dispatchEvent(new Event('change'));
  return {uv_scale_x:2,uv_scale_y:.5};
 },
 armorSnapTest:()=>{
  scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);let target=null;
  const rect=renderer.domElement.getBoundingClientRect();
  bodyRoot.traverse(object=>{
   if(target||!object.isMesh||object.userData.kind!=='body'||object.userData.part!=='hull')return;
   const index=object.geometry.index,pos=object.geometry.attributes.position;
   for(let i=0;i<index.count;i+=3){
    const point=new THREE.Vector3();for(let j=0;j<3;j++)point.add(new THREE.Vector3().fromBufferAttribute(pos,index.getX(i+j)));
    point.multiplyScalar(1/3).applyMatrix4(object.matrixWorld).project(camera);
    if(Math.abs(point.x)>.85||Math.abs(point.y)>.85||Math.abs(point.z)>1)continue;
    raycaster.setFromCamera(new THREE.Vector2(point.x,point.y),camera);
    const hit=raycaster.intersectObject(bodyRoot,true).find(h=>h.object.visible&&h.object.userData.kind==='body');
    if(!hit||hit.object!==object||planarFaces(object,hit.faceIndex).size>5000)continue;
    target={x:rect.left+(point.x+1)*rect.width/2,y:rect.top+(1-point.y)*rect.height/2};break;
   }
  });
  if(target)snapEffect(target.x,target.y);return target;
 },
 armorAdjustTest:()=>{
  const values={uv_scale:.65,uv_scale_x:1.6,uv_scale_y:.7,crop_left:12,crop_top:8,crop_right:0,crop_bottom:0};
  for(const field of document.querySelectorAll('[data-ae-param]')){field.value=values[field.dataset.aeParam];showEffectValue(field);}
  $('aeScale').dispatchEvent(new Event('change'));return values;
 },
 effectState:()=>({frame:effectFrame,frames:effectInfo?.frames,config:effectInfo?.config,rect:effectInfo?.rects[effectFrame],positions:effectMeshes.map(x=>x.position.toArray()),bounds:effectMeshes.map(x=>{x.geometry.computeBoundingBox();return x.geometry.boundingBox.getSize(new THREE.Vector3()).toArray();}),triangles:effectMeshes.map(x=>x.geometry.index.count/3),blend:effectMeshes.map(x=>[x.material.blendSrc,x.material.blendDst]),corners:effectInfo?.corners,base_size:effectInfo?.base_size,handles:handleMeshes.map(h=>[h.userData.handle,h.userData.index]),deform:deformEnabled,errors}),
 deformDragTest:(dx=26,dy=16,kind='corner',index=1,shift=false)=>{
  if(!handleMeshes.length)return null;
  scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);
  const corner=handleMeshes.find(h=>h.userData.handle===kind&&h.userData.index===index)||handleMeshes[0];
  const point=screenPoint(corner),target=renderer.domElement;
  const options={bubbles:true,cancelable:true,pointerId:1,pointerType:'mouse',button:0,buttons:1,clientX:point.x,clientY:point.y,shiftKey:shift};
  target.dispatchEvent(new PointerEvent('pointerdown',options));
  target.dispatchEvent(new PointerEvent('pointermove',{...options,clientX:point.x+dx,clientY:point.y+dy,buttons:1}));
  target.dispatchEvent(new PointerEvent('pointerup',{...options,clientX:point.x+dx,clientY:point.y+dy,buttons:0}));
  const config=effectInfo.config;
  return {corner:[point.x,point.y],delta:[dx,dy],before:{warp_tr_x:config.warp_tr_x,warp_tr_y:config.warp_tr_y,x:config.x,y:config.y,z:config.z}};
 },
 effectTime:time=>{elapsed=time;render();return effectFrame;},
 effectSideView:()=>{
  const box=new THREE.Box3().setFromObject(bodyRoot),center=box.getCenter(new THREE.Vector3()),radius=box.getSize(new THREE.Vector3()).length()/2;
  controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(radius*1.65,radius*.12,0));controls.update();render();
 },
 surfaceClickTest:()=>{
  if(!effectInfo||!bodyRoot)return null;scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);
  const rect=renderer.domElement.getBoundingClientRect();let selected=null;
  bodyRoot.traverse(object=>{
   if(selected||!object.isMesh||object.userData.part!=='hull')return;
   const index=object.geometry.index,pos=object.geometry.attributes.position;
   for(let i=0;i<index.count;i+=3){
    const p=new THREE.Vector3();for(let j=0;j<3;j++)p.add(new THREE.Vector3().fromBufferAttribute(pos,index.getX(i+j)));p.multiplyScalar(1/3).applyMatrix4(object.matrixWorld).project(camera);
    if(Math.abs(p.x)>.9||Math.abs(p.y)>.9||Math.abs(p.z)>1)continue;
    selected=pickEffectFace(rect.left+(p.x+1)*rect.width/2,rect.top+(1-p.y)*rect.height/2,{});if(selected)break;
   }
  });return selected;
 },
 capturePaintTexture:()=>paintCanvas?paintCanvas.toDataURL('image/png'):null,
 paintState:()=>({saved:paintLayers.length,savedTextures:new Set(paintLayers.map(x=>bodyInfo.meshes[x.mesh].texture)).size,placed:!!paintHit,loaded:!!paintImage,preview:!!paintCanvas,mesh:paintHit?.mesh,u:paintHit?.u,v:paintHit?.v,status:$('paintStatus').textContent,pixel:paintCanvas&&paintHit?Array.from(paintCanvas.getContext('2d').getImageData(Math.min(paintCanvas.width-1,Math.floor(paintHit.u*paintCanvas.width)),Math.min(paintCanvas.height-1,Math.floor(paintHit.v*paintCanvas.height)),1,1).data):null}),
 paintTarget:(previous=null)=>{
  if(!bodyRoot)return null;scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);
  let found=null;bodyRoot.traverse(object=>{
   if(found||!object.isMesh||object.userData.kind!=='body')return;
   const entry=bodyInfo.meshes[object.userData.meshIndex];if(!entry?.texture||!(entry.source?.texture||'').toLowerCase().endsWith('_am.dds'))return;
   const idx=object.geometry.getIndex(),pos=object.geometry.getAttribute('position'),rect=renderer.domElement.getBoundingClientRect();
   for(let i=0;i<idx.count;i+=3){
    const point=new THREE.Vector3();for(let j=0;j<3;j++)point.add(new THREE.Vector3().fromBufferAttribute(pos,idx.getX(i+j)));
    point.multiplyScalar(1/3).applyMatrix4(object.matrixWorld).project(camera);
    if(Math.abs(point.x)>.9||Math.abs(point.y)>.9||Math.abs(point.z)>1)continue;
    raycaster.setFromCamera(new THREE.Vector2(point.x,point.y),camera);
    const hit=raycaster.intersectObject(bodyRoot,true).find(h=>h.object.visible&&h.object.userData.kind==='body');
    if(hit&&hit.object===object&&hit.uv&&hit.uv.x>=0&&hit.uv.x<=1&&hit.uv.y>=0&&hit.uv.y<=1&&(!previous||Math.hypot(hit.uv.x-previous.u,hit.uv.y-previous.v)>.3)){found={x:rect.left+(point.x+1)*rect.width/2,y:rect.top+(1-point.y)*rect.height/2,u:hit.uv.x,v:hit.uv.y};break;}
   }
  });return found;
 },
 report:()=>({ready,error:fatal,errors,revision:applied,...stats,bodyMeshes:bodyInfo?.meshes.length||0,lampMeshes:lampInfo?.meshes.length||0,bands:lampInfo?.tracks.length||0,bodyTriangles:bodyInfo?.triangles||0,seconds:elapsed}),
 exercise:()=>{
  const output={};$('play').click();output.paused=paused;$('play').click();
  $('yaw').value='25';$('pitch').value='8';setPose();output.turret=bodyRoot.getObjectByName('turret').rotation.y;
  $('part').value='gun';$('part').dispatchEvent(new Event('change'));output.filter=visiblePart;
  $('part').value='all';$('part').dispatchEvent(new Event('change'));fit();
  output.geometryBounds=bodyRoot?new THREE.Box3().setFromObject(bodyRoot).getSize(new THREE.Vector3()).toArray():[];
  output.webgl2=!!renderer.getContext().texStorage2D;
  let areaObject=null;bodyRoot.traverse(object=>{if(!areaObject&&object.isMesh&&object.userData.kind==='body'&&object.userData.part==='hull')areaObject=object;});
  if(areaObject){const pos=areaObject.geometry.getAttribute('position'),idx=areaObject.geometry.getIndex();const point=new THREE.Vector3();for(let j=0;j<3;j++)point.add(new THREE.Vector3().fromBufferAttribute(pos,idx.getX(j)));point.multiplyScalar(1/3).applyMatrix4(areaObject.matrixWorld).project(camera);const rect=renderer.domElement.getBoundingClientRect(),x=rect.left+(point.x+1)*rect.width/2,y=rect.top+(1-point.y)*rect.height/2;rectangleFaces([x-2,y-2],[x+2,y+2],{});output.areaCount=Array.from(areaFaces.values()).reduce((n,set)=>n+set.size,0);output.areaOverlayCount=areaOverlays.length;areaFaces.clear();refreshArea();}
  $('quality').value='fast';$('quality').dispatchEvent(new Event('change'));render();output.fastBloomDisabled=!bloom.enabled;
  $('quality').value='balanced';$('quality').dispatchEvent(new Event('change'));
  $('bright').click();render();$('bright').click();
  scene.updateMatrixWorld(true);camera.updateMatrixWorld();output.pickable=false;
  if(lampRoot){lampRoot.traverse(object=>{
   if(output.pickable||!object.isMesh)return;
   const p=object.geometry.getAttribute('position'),idx=object.geometry.index;
   for(let i=0;i<Math.min(idx.count,90);i+=3){
    const point=new THREE.Vector3().fromBufferAttribute(p,idx.getX(i)).add(new THREE.Vector3().fromBufferAttribute(p,idx.getX(i+1))).add(new THREE.Vector3().fromBufferAttribute(p,idx.getX(i+2))).multiplyScalar(1/3);
    point.applyMatrix4(object.matrixWorld).project(camera);
    const rect=renderer.domElement.getBoundingClientRect();
    if(Math.abs(point.x)<1&&Math.abs(point.y)<1&&pickAt(rect.left+(point.x+1)*rect.width/2,rect.top+(1-point.y)*rect.height/2)){output.pickable=true;break;}
   }
  });}
  const savedTime=elapsed,gl=renderer.getContext(),width=renderer.domElement.width,height=renderer.domElement.height;
  const before=new Uint8Array(width*height*4),after=new Uint8Array(before.length);
  elapsed=0;render();gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,before);
  elapsed=.41;render();gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,after);
  output.animatedChannels=0;
  for(let i=0;i<before.length;i++)if(i%4!==3&&Math.abs(before[i]-after[i])>2)output.animatedChannels++;
  elapsed=savedTime;dirty=true;
  return output;
 },
 capture:()=>{render();return renderer.domElement.toDataURL('image/png');}
};
if(!fatal){setupPaint();resize();requestAnimationFrame(tick);poll();}
window.addEventListener('beforeunload',()=>{navigator.sendBeacon(url('closed'),JSON.stringify({closed:true}));});

$('aeMirror').onchange=async()=>{try{const response=await post('effectparams',{mirror:$('aeMirror').checked});if(!response.ok)throw Error('双侧设置未应用');$('message').textContent='正在更新左右双侧显示…';}catch(error){$('aeMirror').checked=!!effectInfo.config.mirror;$('message').textContent=String(error);}};

async function sendTint(){
 try{const response=await post('effectparams',{tint_color:$('aeTintColor').value,tint_strength:Number($('aeTintStrength').value)});if(!response.ok){const error=await response.json();throw Error(error.error||'颜色未应用');}$('message').textContent='正在同步特效颜色…';}
 catch(error){$('message').textContent=String(error);}
}
$('aeTintColor').onchange=()=>{if(Number($('aeTintStrength').value)===0)$('aeTintStrength').value=100;$('aeTintValue').textContent=$('aeTintStrength').value+'%';sendTint();};
$('aeTintStrength').oninput=()=>{$('aeTintValue').textContent=$('aeTintStrength').value+'%';};
$('aeTintStrength').onchange=sendTint;
$('aeTintReset').onclick=()=>{$('aeTintStrength').value=0;$('aeTintValue').textContent='0%';sendTint();};

function showAppearanceValue(input){input.nextElementSibling.textContent=Number(input.value).toFixed(input.dataset.aeAppearance==='transparency'?0:2)+(input.dataset.aeAppearance==='transparency'?'%':' 倍');}
let appearanceTimer=null;
async function sendAppearance(){
 const values=Object.fromEntries(Array.from(document.querySelectorAll('[data-ae-appearance]'),input=>[input.dataset.aeAppearance,Number(input.value)]));
 try{const response=await post('effectparams',values);if(!response.ok){const error=await response.json();throw Error(error.error||'外观调整未应用');}$('message').textContent='正在同步亮度、对比度与透明度…';}
 catch(error){$('message').textContent=String(error);}
}
for(const input of document.querySelectorAll('[data-ae-appearance]')){
 input.oninput=()=>{showAppearanceValue(input);clearTimeout(appearanceTimer);appearanceTimer=setTimeout(sendAppearance,150);};
 input.onchange=()=>{clearTimeout(appearanceTimer);sendAppearance();};
}
$('aeAppearanceReset').onclick=()=>{clearTimeout(appearanceTimer);for(const input of document.querySelectorAll('[data-ae-appearance]')){input.value=input.dataset.aeAppearance==='transparency'?0:1;showAppearanceValue(input);}sendAppearance();};
