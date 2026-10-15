import assert from "node:assert/strict";
import {test} from "node:test";
import * as THREE from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import {serializedGpuProbe} from "../../src/flymsg/viz_static/gpu-probe.js";

for (const paged of [false, true]) test(`a failing diagnostic restores state and routes the selected renderer (paged=${paged})`,()=>{
  let discarded=false,drawn=false,target={name:"original"};
  const material={vertexShader:"original shader",needsUpdate:false};
  const viewport=new THREE.Vector4(1,2,3,4),scissor=new THREE.Vector4(5,6,7,8);
  let scissorTest=true;
  const shaderError=()=>{};
  const gl={RASTERIZER_DISCARD:1,isContextLost:()=>false,isEnabled:()=>discarded,
    enable:()=>{discarded=true},disable:()=>{discarded=false},finish:()=>{}};
  const renderer={xr:{isPresenting:false},debug:{onShaderError:shaderError},getContext:()=>gl,
    getRenderTarget:()=>target,setRenderTarget:t=>{target=t},
    getViewport:v=>v.copy(viewport),setViewport:(...args)=>args.length===1?viewport.copy(args[0]):viewport.set(...args),
    getScissor:v=>v.copy(scissor),setScissor:v=>scissor.copy(v),
    getScissorTest:()=>scissorTest,setScissorTest:v=>{scissorTest=v},
    info:{reset:()=>{drawn=false},render:{calls:1,lines:1,triangles:0}},clear:()=>{},
    render:()=>{if(material.vertexShader!=="original shader")throw Error("injected compilation failure");drawn=true},
    readRenderTargetPixels:(_t,_x,_y,_w,_h,pixels)=>{pixels.fill(0);if(drawn&&!discarded)pixels[4]=255},
  };
  const camera={updateMatrixWorld:()=>{},matrixWorld:new THREE.Matrix4(),projectionMatrix:new THREE.Matrix4()};
  const render = renderer.render;
  let routed = 0;
  if (paged) renderer.render = () => { throw new Error("Bypassed application pipeline"); };
  assert.throws(()=>serializedGpuProbe({THREE,renderer,camera,world:{updateMatrixWorld:()=>{}},skeletons:{material},paged:paged?{}:null,renderScene:paged?()=>{routed++;render()}:undefined},
    {sizes:[4],warmup:1,repeats:1}),/injected compilation failure/);
  assert.equal(discarded,false);
  assert.equal(material.vertexShader,"original shader");
  assert.equal(renderer.debug.onShaderError,shaderError);
  assert.equal(target.name,"original");
  assert.deepEqual(viewport.toArray(),[1,2,3,4]);
  assert.deepEqual(scissor.toArray(),[5,6,7,8]);
  assert.equal(scissorTest,true);
  if (paged) assert(routed > 0);
});
