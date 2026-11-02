// Exercise the actual preview functions with in-memory meshes; no browser/UI.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const code = fs.readFileSync(process.argv[2], 'utf8');
function extract(begin, end) {
  const a = code.indexOf(begin), b = code.indexOf(end, a + begin.length);
  assert(a >= 0 && b > a); return code.slice(a, b);
}
function geometry() {
  const attr = {array: new Float32Array(3), needsUpdate: false};
  return {attributes: {position: attr}, bounds: 0, computeBoundingSphere() { this.bounds++; }};
}
function vector(x, y, z) {
  return {x, y, z, clone() {return vector(this.x, this.y, this.z);}, set(a,b,c) {this.x=a;this.y=b;this.z=c;return this;}};
}
function mesh(x) {
  return {geometry: geometry(), position: vector(x,0,0), getWorldPosition(v) {v.marker=x;return v;}};
}
const meshes = [mesh(-2), mesh(2)];
meshes.forEach(m => {m.position.set = function(x,y,z) {this.x=x;this.y=y;this.z=z;};});
let anchor = null;
const context = {
  effectMeshes: meshes, effectInfo: {weights: [[1,0,0,0]], corners: [], config: {plane:'side',placement:'plane'}},
  effectDrag: null, handleMeshes: [], dirty: false,
  THREE: {Vector3: function(){}, MathUtils: {degToRad: x => x * Math.PI / 180}},
  camera: {position: {distanceTo: () => 10}, fov: 45},
  renderer: {domElement: {clientHeight: 600, setPointerCapture() {}}},
  controls: {enabled:true}, $: () => ({textContent:''}),
  planeRayHit: (x,y,p) => {if (p.marker !== undefined) anchor=p.marker;return {};},
  localDeltaFromWorld: () => vector(1,2,3)
};
vm.createContext(context);
vm.runInContext(extract('function applyDraggedCorners(', 'async function finishEffectDrag('), context);
context.applyDraggedCorners([vector(4,5,6),vector(0,0,0),vector(0,0,0),vector(0,0,0)]);
for (const [index,m] of meshes.entries()) {
  assert.deepStrictEqual(Array.from(m.geometry.attributes.position.array),[index===0?4:-4,5,6]);
  assert.strictEqual(m.geometry.attributes.position.needsUpdate,true);
  assert.strictEqual(m.geometry.bounds,1);
}
const event={clientX:10,clientY:20,pointerId:1,shiftKey:false};
assert(context.startEffectDrag(event,null,meshes[1]));
assert.strictEqual(anchor,2);assert.strictEqual(context.effectDrag.pickedIndex,1);
context.moveEffectDrag(event);
assert.deepStrictEqual([meshes[0].position.x,meshes[0].position.y,meshes[0].position.z],[-3,2,3]);
assert.deepStrictEqual([meshes[1].position.x,meshes[1].position.y,meshes[1].position.z],[3,2,3]);
assert(code.includes('startEffectDrag(e,null,hit.object)'));
vm.runInContext(extract('function effectMeshArrays(', 'function loadEffect('), context);
const info={config:{placement:'plane'},vertices:[[.4,1,2],[.2,2,3],[-.1,3,4]],indices:[0,1,2]};
const primary=context.effectMeshArrays(info,0),reflected=context.effectMeshArrays(info,1);
assert.deepStrictEqual(Array.from(primary.positions),[.4,1,2,.2,2,3,-.1,3,4]);
assert.deepStrictEqual(Array.from(reflected.positions),[-.4,1,2,-.2,2,3,.1,3,4]);
assert.deepStrictEqual(Array.from(reflected.indices),[0,2,1]);
console.log('MIRRORED_DRAG_BOTH_GEOMETRIES_AND_PICKED_SIDE_OK');
