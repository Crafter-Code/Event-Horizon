                                                                               
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tm=t=>`${String(Math.floor(t/60)).padStart(2,'0')}:${String(Math.floor(t%60)).padStart(2,'0')}`;
  const incoming=new URLSearchParams(location.search);
  let manifest,last,selected,layout='studio',playing=false,at=0,wall=performance.now(),speed=1;
  let generation=0,controller=null,clipStart=null,clipEnd=5400;const motion=window.EHField.createMotion();let renderedFrames=0;
  function mediaTime(){return playing?Math.min(clipEnd,at+(performance.now()-wall)/1000*speed):at;}
  function setLayout(value){layout=['studio','broadcast','stream'].includes(value)?value:'studio';$('screen').dataset.layout=layout;document.querySelectorAll('button[data-layout]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.layout===layout)));}
  function stop(){at=last?.clock||at;playing=false;if(last?.observation)motion.push(last.observation,last.run_key,{snap:true});$('play').textContent='Play';}
  function clearCaption(){
    $('headline').textContent='Waiting for a complete episode';$('caption').textContent='The result appears only after it is known at this replay time.';
    $('episode-at').textContent='';$('chain').replaceChildren();$('fact-hash').textContent='';$('checks').replaceChildren();
    $('chain-note').textContent='No future outcome is revealed during the build-up.';
  }
  function fail(message){stop();$('error').textContent=message;$('error').hidden=false;$('status').textContent='Preview paused';
                                                                            
    clearCaption();$('headline').textContent='Preview unavailable';$('caption').textContent='Resume after the source is available.';
    $('picture').removeAttribute('src');$('studio-pitch').hidden=true;$('score').textContent='— : —';$('screen-stats').replaceChildren();
    $('proof-title').textContent='Preview held';$('proof-explanation').textContent=message;
  }
  function commit(scene,image){
    last=scene;$('picture').src=image.src;const canvas=$('studio-pitch');canvas.dataset.renderClock='';canvas.hidden=!scene.observation;$('picture').hidden=!!scene.observation;if(scene.observation)motion.push(scene.observation,scene.run_key,{snap:!playing});$('picture').dataset.clock=scene.clock;$('screen').dataset.clock=scene.clock;
    $('score').textContent=scene.score.join(' : ');$('clock').textContent=tm(scene.clock);$('seek').value=scene.clock;
    $('clip-time').textContent=tm(scene.clock)+' / 90:00';$('error').hidden=true;
    const s=scene.statistics;
    $('screen-stats').innerHTML=[['Passes',s.passes.map((p,i)=>p+'/'+s.attempts[i]).join(' · '),'completed / attempted'],['Shots',s.shots.join(' · '),'Blue · Red'],['Possession',s.possession.map(p=>p+'%').join(' · '),'in-play time'],['Pressure',s.pressure.join(' · '),'near the ball now']].map(([label,value,note])=>`<div>${esc(label)}<b>${esc(value)}</b><span>${esc(note)}</span></div>`).join('');
    clearCaption();
    if(scene.card){const c=scene.card;
      $('headline').textContent=c.title;$('caption').textContent=c.caption;
      $('episode-at').textContent='EPISODE '+tm(c.episode_time)+' · SOURCE-DERIVED FACTS';
      $('fact-hash').textContent='Shared scene fingerprint · '+c.fact_fingerprint;
      $('chain').innerHTML=c.steps.map(step=>`<li><a href="${esc(step.href)}" target="_blank" rel="noopener"><span>${tm(step.time)} · #${step.event_id}</span><b>${esc(step.label)}</b><span>${esc(step.actors.join(' → '))}</span></a></li>`).join('');
      $('chain-note').textContent=c.explanation;
      clipStart=c.steps[0].time;clipEnd=Math.min(5400,c.available_at+3);$('build-up').disabled=false;
    }
    if(scene.integrity)$('checks').innerHTML=scene.integrity.checks.map(c=>`<li class="${c.passed?'':'failed'}">${esc(c.label)}</li>`).join('');
    $('proof-title').textContent=scene.status==='ready'?'Checked against the source':scene.status==='held'?'Episode held':'Build-up in progress';
    $('proof-explanation').textContent=scene.status==='ready'?'The three scenes share this episode’s facts and source references.':scene.status==='held'?'A source check failed. The episode is withheld from every scene.':'Keep watching. The complete episode will appear when its outcome is known.';
    $('status').textContent=playing?'Rehearsing':'Paused replay';
    $('scene-json').href='/studio/scene?'+new URLSearchParams({at:scene.clock,episode:selected,run_key:manifest.run_key});
    if(playing&&scene.clock>=clipEnd-.05){stop();$('status').textContent='Rehearsal complete';}
  }
  async function refresh(force=false){
    if(!manifest||controller&&!force)return;
    if(controller)controller.abort();const active=new AbortController();controller=active;const id=++generation;
    const query=new URLSearchParams({at:mediaTime(),run_key:manifest.run_key});if(selected)query.set('episode',selected);
    const timeout=setTimeout(()=>active.abort(),8000);
    try{
      const response=await fetch('/studio/scene?'+query,{cache:'no-store',signal:active.signal});if(!response.ok)throw Error('Scene request failed ('+response.status+')');
      const scene=window.EHStudio.validate(await response.json(),manifest.run_key);
      const image=new Image();image.src='data:image/png;base64,'+scene.frame_png;if(!scene.observation)await image.decode();
      if(id!==generation||active.signal.aborted)return;commit(scene,image);
    }catch(error){if(id===generation)fail(error.name==='AbortError'?'The source did not respond in time. The preview has been cleared.':'The scene could not be verified. The preview has been cleared.');}
    finally{clearTimeout(timeout);if(controller===active)controller=null;}
  }
  function seek(value){motion.reset();at=value;wall=performance.now();refresh(true);}
  document.querySelectorAll('button[data-layout]').forEach(b=>b.onclick=()=>setLayout(b.dataset.layout));
  $('guides').onchange=()=>{$('safe-guide').hidden=!$('guides').checked;};
  $('play').onclick=()=>{if(playing)stop();else{if(at>=clipEnd)at=clipStart??0;wall=performance.now();playing=true;$('play').textContent='Pause';}refresh(true);};
  $('build-up').onclick=()=>{if(clipStart===null)return;playing=true;$('play').textContent='Pause';seek(clipStart);};
  $('speed').onchange=()=>{at=mediaTime();wall=performance.now();speed=Number($('speed').value);};
  $('seek').oninput=()=>{playing=false;$('play').textContent='Play';clipEnd=5400;seek(Number($('seek').value));};
  $('episode').onchange=()=>{selected=$('episode').value;const e=manifest.episodes.find(e=>e.id===selected);playing=false;clipEnd=5400;clipStart=null;$('build-up').disabled=true;$('play').textContent='Play';seek(e.available_at);};
  $('share').onclick=async()=>{if(!last)return;const link=window.EHStudio.link(location.origin,last,layout);try{await navigator.clipboard.writeText(link);$('status').textContent='Rehearsal link copied';}catch{$('status').textContent='Link is in the address bar';history.replaceState(null,'',link);}};
  setLayout(incoming.get('layout'));
  fetch('/demo/manifest',{cache:'no-store',signal:AbortSignal.timeout(10000)}).then(async response=>{
    if(!response.ok)throw Error('Archive unavailable');manifest=await response.json();
    if(incoming.has('run_key')&&incoming.get('run_key')!==manifest.run_key)throw Error('This rehearsal link belongs to another match archive.');
    const episodes=manifest.episodes.filter(e=>e.verified&&e.kind!=='trend');
    selected=incoming.get('episode')||episodes.find(e=>e.kind==='goal')?.id||episodes[0]?.id;
    const episode=episodes.find(e=>e.id===selected);if(!episode)throw Error('Rehearsal episode unavailable.');
    $('episode').innerHTML=episodes.map(e=>`<option value="${esc(e.id)}">${tm(e.time)} · ${esc(e.kind==='goal'?'Goal':e.kind==='counterattack'?'Fast attack':'Shot')} · ${e.team?'Red':'Blue'}</option>`).join('');$('episode').value=selected;
    at=incoming.has('at')?Number(incoming.get('at')):episode.available_at;
    if(!Number.isFinite(at)||at<0||at>5400)throw Error('Invalid rehearsal time.');
    for(const id of ['play','seek','episode','share'])$(id).disabled=false;
    await refresh(true);
  }).catch(error=>fail(error.message));
  function drawFrame(){const canvas=$('studio-pitch');if(last?.observation&&!canvas.hidden&&!document.hidden){const o=motion.sample();if(o&&canvas.dataset.renderClock!==String(o.time)){window.EHField.draw(canvas.getContext('2d'),canvas,o,{player:'none',metrics:[]});canvas.dataset.renderClock=o.time;canvas.dataset.renderFrames=++renderedFrames;canvas.dataset.sourceClock=last.clock;}}requestAnimationFrame(drawFrame);}requestAnimationFrame(drawFrame);
  setInterval(()=>{if(playing&&!document.hidden)refresh();},100);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  window.addEventListener('resize',()=>{$('studio-pitch').dataset.renderClock='';});
})();
