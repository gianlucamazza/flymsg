// Synthetic non-immersive context loss on one explicit local diagnostic page.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { localObserver } from "./observer_cdp.mjs";
const [endpoint, target, out] = process.argv.slice(2);
if (!endpoint || !target || !out)
  throw Error(
    "usage: observer_context.mjs LOCAL_CDP_ENDPOINT TARGET_ID NEW_DIRECTORY",
  );
const browser = await localObserver(endpoint, target);
try {
  mkdirSync(out, { recursive: false });
  writeFileSync(
    join(out, "implementation.mjs"),
    readFileSync(new URL(import.meta.url)),
    { flag: "wx" },
  );
  const result = await browser.evaluate(`(async()=>{
    if(flymsg.renderer.xr.isPresenting)throw Error('Non-immersive test required');
    const saved=flymsg.diagnostic({continuous:false,time:20,playing:false,residentLines:true});
    try {
      const ready=async()=>{const until=performance.now()+30000;
        while(flymsg.paged&&flymsg.paged.state!=='ready'&&performance.now()<until)await new Promise(resolve=>setTimeout(resolve,100));
        if(flymsg.paged&&flymsg.paged.state!=='ready')throw Error('GPU recovery incomplete; no completed artifact')};
      await ready();
      const options={width:64,height:64,time:20,culling:true,pipeline:flymsg.paged?'paged':'original'};
      const before=await flymsg.reference(options);
      const canvas=flymsg.renderer.domElement,gl=flymsg.renderer.getContext();
      const extension=gl.getExtension('WEBGL_lose_context');
      if(!extension)throw Error('Synthetic context loss unavailable');
      const events=[];
      await new Promise((resolve,reject)=>{
        const finish=error=>{clearTimeout(timeout);canvas.removeEventListener('webglcontextlost',lost);canvas.removeEventListener('webglcontextrestored',restored);error?reject(error):resolve()};
        const lost=e=>{e.preventDefault();events.push({type:'lost',at:new Date().toISOString()});setTimeout(()=>extension.restoreContext(),100)};
        const restored=()=>{events.push({type:'restored',at:new Date().toISOString()});finish()};
        const timeout=setTimeout(()=>finish(Error('Context restoration timeout; no completed artifact')),20000);
        canvas.addEventListener('webglcontextlost',lost);canvas.addEventListener('webglcontextrestored',restored);
        extension.loseContext();
      });
      if(gl.isContextLost())throw Error('Context remains lost');
      await ready();
      const after=await flymsg.reference(options);
      for(const key of Object.keys(before.images))
        if(before.images[key].sha256!==after.images[key].sha256)throw Error('Restored image differs: '+key);
      if(JSON.stringify(before.geometry)!==JSON.stringify(after.geometry))throw Error('Restored geometry differs');
      return {schema:'flymsg.nonimmersive-context-recovery/v1',renderer_pipeline:options.pipeline,events,before,after,
        resources:flymsg.resources(),fidelity:flymsg.fidelity(),qualification:'Synthetic direct-render recovery only; not immersive lifecycle or compositor qualification'};
    } finally {flymsg.diagnostic(saved)}
  })()`);
  writeFileSync(
    join(out, "recovery.json"),
    JSON.stringify(
      { url: browser.url, recorded_at: new Date().toISOString(), ...result },
      null,
      2,
    ) + "\n",
    { flag: "wx" },
  );
  console.log(
    "Direct-render context recovery: colour, ID, depth and geometry identical",
  );
} finally {
  browser.close();
}
