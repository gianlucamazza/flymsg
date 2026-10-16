import assert from "node:assert/strict";
import {test} from "node:test";
import {selectFidelity} from "../../src/flymsg/viz_static/fidelity.js";
const neurons=[{key:0,manifest:{lods:[[{size:100},{size:200}], [{size:1}]]}},{key:1,manifest:{lods:[[{size:300}], [{size:1}]]}}];
test("capacity exhaustion never substitutes skeletons or admits a partial selection",()=>{
  const r=selectFidelity(neurons,"surface",599,1);
  assert.equal(r.status,"unsupported"); assert.equal(r.meshes.size,0); assert.deepEqual(r.skeletons,[]);
  const full=selectFidelity(neurons,"surface",600,1);
  assert.equal(full.status,"ready"); assert.deepEqual([...full.meshes],[[0,[{lod:0,i:0},{lod:0,i:1}]],[1,[{lod:0,i:0}]]]);
});
test("missing source differs from loading and is never masked by skeleton fallback",()=>{
  assert.equal(selectFidelity([{key:0,manifest:null}],"surface",100,1).status,"loading");
  const r=selectFidelity([{key:0,manifest:null,missing:true},{key:1,manifest:null}],"surface",100,1);
  assert.equal(r.status,"unsupported"); assert.equal(r.reasons.length,2);assert.equal(r.meshes.size,0);
});
test("explicit skeleton selection preserves every selected neuron without surface work",()=>{
  const r=selectFidelity(neurons,"skeleton",0,1);
  assert.deepEqual(r.skeletons,[0,1]);assert.equal(r.meshes.size,0);
  assert.throws(()=>selectFidelity(neurons,"auto",100,1),RangeError);
});
