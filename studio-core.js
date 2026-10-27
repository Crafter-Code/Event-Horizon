                                                                               
(function(root){
  'use strict';
  function validate(scene,runKey){
    if(scene.schema_version!=='eh-media-scene-1'||scene.run_key!==runKey||scene.mode!=='rehearsal'||!Number.isFinite(scene.clock))throw Error('Scene identity changed');
    if(!['waiting','ready','held'].includes(scene.status))throw Error('Unknown scene status');
    if(scene.card){
      if(scene.status!=='ready'||scene.integrity?.status!=='passed'||!scene.integrity.checks.length||!scene.integrity.checks.every(c=>c.passed===true))throw Error('Unverified scene');
      if(scene.card.available_at>scene.clock||scene.card.steps.some(s=>s.time>scene.clock))throw Error('Future evidence');
      for(const layout of ['studio','broadcast','stream'])if(scene.layouts[layout]?.fact_fingerprint!==scene.card.fact_fingerprint)throw Error('Scene facts disagree');
    }else if(scene.status==='ready')throw Error('Missing scene card');
    return scene;
  }
  function link(origin,scene,layout){
    const url=new URL('/studio',origin);
    url.search=new URLSearchParams({at:scene.clock,episode:scene.card?.facts.episode_id||'',layout,run_key:scene.run_key}).toString();
    if(!scene.card)url.searchParams.delete('episode');
    return url.href;
  }
  const api={validate,link};
  if(typeof module!=='undefined')module.exports=api;else root.EHStudio=api;
})(globalThis);
