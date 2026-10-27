                                                                                
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clock=t=>`${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')}`;
  const readonly=document.body.dataset.readonly==='true';
  let last=null,busy=false,epoch=0,polling=false,seenRun=null;
  $('readonly').hidden=!readonly;
  function controls(running=false){
    for(const id of ['seed','duration','speed','start'])$(id).disabled=readonly||busy||running;
    $('stop-run').disabled=readonly||busy||!running;
  }
  function lane(title,subtitle,data){
    const m=data.metrics;
    return `<section class="lane"><div class="eyebrow">${title}</div><h2>${subtitle}<span class="clock">${clock(data.clock)}</span></h2><div class="stats"><div>Score<b>${m.score.join(' : ')}</b></div><div>Passes<b>${m.passes.join(' · ')}</b></div><div>Shots<b>${m.shots.join(' · ')}</b></div></div><small>Possession ${m.possession.join('% · ')}% · ${data.event_count} events · tick ${data.tick}</small><div class="hash">Event SHA-256<br>${esc(data.event_sha256)}</div><ul class="feed">${data.recent_events.map(e=>`<li><span>${clock(e.time)} · #${e.id}</span><b>${esc(e.title)}</b></li>`).join('')}</ul><div class="timing"><span>Analysis p95</span><b>${data.analysis_p95_ms===null?'Awaiting events':data.analysis_p95_ms+' ms'}</b></div></section>`;
  }
  function render(s){
    if(s.schema_version!=='eh-replay-proof-1'||!['idle','running','passed','failed','stopped'].includes(s.status))throw Error('Unexpected verification response');
    last=s;$('error').hidden=true;document.body.classList.remove('stale');controls(s.status==='running');
    $('result').dataset.status=s.status;
    $('verdict').textContent={idle:'Ready to compare',running:'Comparing every received tick',passed:'Every event matched',failed:'Verification failed · see details',stopped:'Stopped · partial comparison'}[s.status];
    $('receipt').hidden=s.status!=='passed';
    if(s.run_key)$('receipt').href='/replay-lab/receipt?'+new URLSearchParams({run_key:s.run_key});
    if(s.status==='idle')return;
    if(s.run_key!==seenRun){$('seed').value=s.identity.settings.seed;$('duration').value=s.identity.duration_seconds;$('speed').value=s.speed;seenRun=s.run_key;}
    $('mode').textContent=`${s.speed}× ${s.speed===1?'real time':'demonstration'} · ${s.delivery_window_ms} ms delivery windows`;
    $('matched').textContent=clock(s.matched_seconds);$('events').textContent=s.compared_events;$('backlog').textContent=s.backlog_seconds.toFixed(2);
    const percent=100*s.matched_seconds/s.identity.duration_seconds;
    $('progress-fill').style.width=percent+'%';$('progress').setAttribute('aria-valuenow',String(Math.round(percent)));
    $('repeat').textContent=s.previous_run_match===true?'This repeat also matches the previous completed run.':s.previous_run_match===false?'The result differs from the previous run with the same identity.':s.status==='passed'?'Repeat with these settings to compare against this completed run.':'Results cover only the match time already compared.';
    $('lanes').innerHTML=lane('Run A · steady schedule','Reference',s.reference)+lane('Run B · uneven delivery','Stream',s.stream);
    $('identity').textContent=JSON.stringify(s.identity,null,2);
    $('mismatch').hidden=!(s.first_mismatch||s.error);
    $('mismatch').textContent=JSON.stringify(s.first_mismatch||s.error,null,2);
    $('start').textContent=s.status==='passed'&&Number($('seed').value)===s.identity.settings.seed&&Number($('duration').value)===s.identity.duration_seconds?'Run again':'Compare runs';
  }
  function fail(message){$('error').textContent=message;$('error').hidden=false;document.body.classList.add('stale');$('verdict').textContent='Connection unavailable · showing last confirmed result';$('receipt').hidden=true;}
  async function request(path,body){
    const response=await fetch(path,{cache:'no-store',signal:AbortSignal.timeout(8000),...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
    if(!response.ok){if(response.status===401)throw Error('Editor sign-in is required. Open editor controls.');throw Error((await response.json()).error||'Verification unavailable');}
    return response.json();
  }
  async function poll(){if(polling||busy)return;polling=true;const turn=epoch;try{const s=await request('/replay-lab/state');if(turn===epoch)render(s);}catch(error){if(turn===epoch)fail(error.message);}finally{polling=false;}}
  async function action(path,body){busy=true;epoch++;controls(last?.status==='running');try{render(await request(path,body));}catch(error){fail(error.message);}finally{busy=false;controls(last?.status==='running');poll();}}
  $('controls').onsubmit=event=>{event.preventDefault();if(readonly||busy)return;action('/replay-lab/start',{seed:Number($('seed').value),seconds:Number($('duration').value),speed:Number($('speed').value)});};
  $('stop-run').onclick=()=>{if(last&&!readonly&&!busy)action('/replay-lab/stop',{run_key:last.run_key});};
  controls();poll();setInterval(()=>{if(!document.hidden)poll();},350);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
})();
