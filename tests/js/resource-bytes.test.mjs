import assert from "node:assert/strict";
import {test} from "node:test";
import {bufferBytes} from "../../src/flymsg/viz_static/resource-bytes.js";
test("byte accounting deduplicates aliased retained backing stores",()=>{
  const backing = new ArrayBuffer(1024);
  assert.equal(bufferBytes([new Uint8Array(backing,0,10),new Float32Array(backing,512,4),new Uint32Array(3),null]),1036);
});
