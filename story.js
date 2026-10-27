                                                                                    
(()=>{
  const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tm=s=>`${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;
  const copy={

    de:{"period":"Ein Zeitraum · zwei Perspektiven","wait":"Der Vergleich zweier vollständiger Minuten beginnt nach 02:00.","prior":"Vorher","current":"Aktuell","delta":"Veränderung","facts":"Gemeinsame Fakten","sources":"Belege","waiting":"Warten auf die nächste Szene","live":"Im Spielverlauf","time":"Anzeigezeitpunkt","json":"Materialien als JSON","output":"Externe Anzeige","health":"Materialien und Anzeigeverzögerung","noLatency":"Verzögerung: Warten auf die Anzeige einer neuen Karte.","latency":"Ereignis → Anzeigebestätigung","upper":"Obergrenze: einschließlich Rückweg der Browserbestätigung. Misst nicht die Lesezeit.","processing":"Bis Material bereit ist","render":"Antwort → Darstellung","sample":"Messungen","focus":"Spielerfokus","passes":"Pässe","shots":"Schüsse","tackles":"Balleroberungen","distance":"Strecke während aktiver Spielzeit","speed":"Geschwindigkeit","moments":"Beteiligung an Schlüsselszenen","none":"Noch keine erfasste Beteiligung an Schlüsselszenen.","now":"Aktuelle Veränderung","pressure":"Veränderung des Drucks, s","tempo":"Veränderung der begonnenen Pässe/min","initiative":"Schussbilanz verschob sich zugunsten von","noShift":"Kein bestätigter Wechsel des Schussvorteils.","boundary":"Verglichen mit den vorherigen 60 Sekunden."},
    en:{period:'One period · two perspectives',wait:'A comparison of two complete minutes starts after 02:00.',prior:'Previous',current:'Current',delta:'Change',facts:'Shared facts',sources:'Evidence',waiting:'Waiting for the next episode',live:'As the match unfolds',time:'Display time',json:'Materials JSON',output:'External display',health:'Materials and display latency',noLatency:'Latency: waiting for a fresh card to be visible.',latency:'Event → display acknowledgement',upper:'Upper bound: includes the browser acknowledgement trip. It does not measure human reading.',processing:'Until material ready',render:'Response → rendering',sample:'Samples',focus:'Player focus',passes:'Passes',shots:'Shots',tackles:'Tackles',distance:'In-play distance',speed:'Speed',moments:'Involvement in key moments',none:'No recorded involvement in key moments yet.',now:'Live change',pressure:'Pressure change, s',tempo:'Pass starts/min change',initiative:'Shot balance shifted towards',noShift:'No confirmed reversal of the shot advantage.',boundary:'Compared with the previous 60 seconds.'},
    cs:{period:'Jeden úsek · dva pohledy',wait:'Porovnání dvou celých minut začne po 02:00.',prior:'Dříve',current:'Nyní',delta:'Změna',facts:'Společná fakta',sources:'Podklady',waiting:'Čekáme na další epizodu',live:'V průběhu zápasu',time:'Čas zobrazení',json:'Podklady JSON',output:'Externí obrazovka',health:'Podklady a zpoždění zobrazení',noLatency:'Zpoždění: čekáme na zobrazení nové karty.',latency:'Událost → potvrzení zobrazení',upper:'Horní mez zahrnuje zpáteční požadavek prohlížeče. Nejde o dobu čtení člověkem.',processing:'Do přípravy podkladu',render:'Odpověď → vykreslení',sample:'Měření',focus:'Hráč v centru',passes:'Přihrávky',shots:'Střely',tackles:'Odebrání',distance:'Dráha ve hře',speed:'Rychlost',moments:'Účast v klíčových momentech',none:'Účast v klíčových momentech zatím není doložena.',now:'Živá změna',pressure:'Změna tlaku, s',tempo:'Změna přihrávek/min',initiative:'Bilance střel se obrátila k týmu',noShift:'Obrat převahy ve střelách není potvrzen.',boundary:'Ve srovnání s předchozími 60 sekundami.'}
  };
  for(const id of ['live-material','period-comparison','continuous-focus','delivery-health','overlay-story'])$(id).dataset.localized='true';
  const teams={de:['Blau','Rot'],en:['Blue','Red'],cs:['Modří','Červení']};
  let data=null,request={},focus=null,received=0,cardKey='',periodKey='',healthKey='',acked=new Set(),inflight=new Set(),retryAt=new Map(),run='';
  function settings(){return window.EHSettings();}
  function query(){const p=settings();return new URLSearchParams({audience:p.audience,language:p.language,team:p.team,player:p.player,metrics:p.metrics.join(','),channel:p.role==='editor'?'broadcast':'viewer'});}
  function active(){if(!data)return null;const p=settings();if(p.role==='editor'&&data.channel!=='broadcast')return null;if(data.language&&data.language!==p.language)return null;const cue=data.active_overlay;const now=data.match_clock+(performance.now()-received)/1000;return cue&&now>=cue.show_at&&now<cue.remove_at&&performance.now()-received<2500?cue:null;}
  function renderCard(){const p=settings(),l=copy[globalThis.EHLocale?.base(p.language)??p.language],cue=active(),el=$('live-material');
    const key=cue?cue.overlay_id+':'+cue.revision+':'+p.language:'empty:'+p.language;
    if(key!==cardKey){cardKey=key;el.dataset.materialId=cue?.material_id||'';
      el.innerHTML=cue?`<div class="section-label">${tm(cue.episode_time)} · ${l.live}</div><h3>${esc(cue.text.event)}</h3><p>${esc(cue.text.significance)}</p><div class="note">${l.sources}</div><div class="source-links">${cue.source_event_ids.slice(0,6).map(id=>`<a href="/event?${new URLSearchParams({id,run_key:data.run_key,language:p.language})}" target="_blank" rel="noopener">#${id}</a>`).join(' ')}<a href="/materials?${query()}" target="_blank" rel="noopener">JSON</a></div>`:`<p class="muted">${l.waiting}</p>`;
    }
    $('overlay-story').hidden=!p.overlay||!cue;
    const now=data.match_clock+(performance.now()-received)/1000;
    $('overlay-stats').hidden=!p.overlay||!data.overlays.some(c=>c.layer==='statistics'&&c.show_at<=now&&now<c.remove_at)||performance.now()-received>2500;
    if(cue){$('title-over').textContent=cue.text.event;$('explanation-over').textContent=cue.text.significance;}
    attemptAck();
  }
  function renderPeriod(){
    const rhythmPrefs=settings();window.EHRhythmLens?.update($('live-rhythm'),data.rhythm,{language:rhythmPrefs.language,audience:rhythmPrefs.audience,metrics:rhythmPrefs.metrics,runKey:data.run_key});
    const p=settings(),l=copy[globalThis.EHLocale?.base(p.language)??p.language],record=data.period,container=$('period-comparison');
    const key=(record?.fact_fingerprint||'opening')+p.audience+p.language+p.metrics.join(',')+p.team;
    if(key!==periodKey){
      periodKey=key;
      const labels={de:['Fan','Analyse'],en:['Fan','Analyst'],cs:['Fanoušek','Analytik']}[globalThis.EHLocale?.base(p.language)??p.language];
      const row=entry=>`<div class="context-row"><span>${esc(entry.label)}</span><strong>${entry.previous===null?'—':esc(entry.previous)+(entry.key==='possession'?'%':'')}</strong><strong>${esc(entry.current)}${entry.key==='possession'?'%':''}</strong><strong>${entry.delta===null?'—':(entry.delta>0?'+':'')+esc(entry.delta)+(entry.key==='possession'?({de:' Pp.',en:' pp',cs:' p. b.'}[globalThis.EHLocale?.base(p.language)??p.language]):'')}</strong></div>`;
      const mirrors=record?.perspectives||[];
      const body=mirrors.map(pair=>`<section class="perspective-pair" aria-label="${esc(l.period)}"><div class="perspective-team">${esc(teams[globalThis.EHLocale?.base(p.language)??p.language][pair.team])}</div><div class="perspective-grid"><article class="period-side"><span class="perspective-role">${labels[0]}</span><h3>${esc(pair.fan.headline)}</h3></article><article class="period-side"><span class="perspective-role">${labels[1]}</span><h3>${esc(pair.analyst.headline)}</h3><div class="context-row"><span></span><span>${l.prior}</span><span>${l.current}</span><span>${l.delta}</span></div>${pair.analyst.rows.map(row).join('')}<p class="note">${esc(pair.analyst.boundary)}</p></article></div></section>`).join('');
      container.innerHTML=`<div class="section-label">${l.period}${record?' · '+tm(record.time-60)+'–'+tm(record.time):''}</div>`+(record?body+`<span class="fact-tag">${l.facts} · ${esc(record.fact_fingerprint.slice(0,12))}</span><details><summary>${l.sources} · ${record.evidence_ids.length}</summary><p class="note">${record.evidence_ids.map(id=>'#'+id).join(' · ')}</p><a href="/materials?${query()}" target="_blank" rel="noopener">${l.json}</a></details>`:`<p>${l.wait}</p>`)+`<div id="live-change-note" class="note"></div>`;
    }
    const note=$('live-change-note');note.hidden=p.audience!=='analyst';
    if(p.audience==='analyst')note.innerHTML=data.live_changes.filter(v=>v.comparable).map(v=>`${l.now} · ${teams[globalThis.EHLocale?.base(p.language)??p.language][v.team]}: ${p.metrics.includes('pressure')?l.pressure+' '+(v.changes.pressure[v.team]>0?'+':'')+v.changes.pressure[v.team]+'. ':''}${p.metrics.includes('tempo')?l.tempo+' '+(v.changes.tempo[v.team]>0?'+':'')+v.changes.tempo[v.team]+'. ':''}${v.changes.initiative_shift===null?l.noShift:l.initiative+' '+teams[globalThis.EHLocale?.base(p.language)??p.language][v.changes.initiative_shift]}`).join('<br>');
  }
  function renderFocus(){const p=settings(),l=copy[globalThis.EHLocale?.base(p.language)??p.language],el=$('continuous-focus');el.hidden=p.audience!=='player'||p.role==='editor'||!focus;if(el.hidden)return;
    const f=focus.player,s=focus.statistics,m=focus.movement;
    el.innerHTML=`<strong>${l.focus} · ${teams[globalThis.EHLocale?.base(p.language)??p.language][f.team]} #${f.number}</strong>${p.metrics.includes('passes')?`<span>${l.passes} ${s.passes}/${s.attempts}</span>`:''}${p.metrics.includes('shots')?`<span>${l.shots} ${s.shots}</span>`:''}${p.metrics.includes('tackles')?`<span>${l.tackles} ${s.tackles}</span>`:''}${p.metrics.includes('movement')?`<span>${l.distance} ${m.distance_m.toFixed(1)} m</span><span>${l.speed} ${m.speed_mps.toFixed(1)} m/s</span>`:''}`;
    const box=$('focus-involvement')||document.createElement('div');box.id='focus-involvement';box.className='note';
    box.innerHTML=`<strong>${l.moments}</strong><br>`+(data.focus_moments.length?data.focus_moments.map(moment=>`<button class="focus-moment" data-episode="${esc(moment.material_id)}">${tm(moment.time)} · ${esc(moment.title)}</button>`).join(' '):l.none);
    if(!box.parentElement)$('player-focus').append(box);for(const button of box.querySelectorAll('button'))button.onclick=()=>window.EHChooseEpisode(button.dataset.episode);
  }
  function renderHealth(){const p=settings(),l=copy[globalThis.EHLocale?.base(p.language)??p.language],timing=data.latency,latest=timing.latest;
    $('latency-strip').textContent=latest?`${l.latency}: ≤${latest.event_to_display_ack_ms.toFixed(1)} ms · p95 ≤${timing.p95_ms.toFixed(1)} ms` : l.noLatency;
    $('latency-strip').title=l.upper;
    $('delivery-heading').textContent=l.health;
    const detail=$('delivery-detail');const cue=data.active_overlay;
    const key=[data.viewer_key,p.role,timing.sample_count,cue?.overlay_id,cue?.revision].join(':');if(healthKey===key)return;healthKey=key;const wasOpen=detail.querySelector('details')?.open;
    detail.innerHTML=`<p>${l.upper}</p><p>${l.sample}: ${timing.sample_count}${latest?` · ${l.processing}: ${latest.processing_ms} ms · ${l.render}: ${latest.browser_render_ms} ms · #${latest.event_id}`:''}</p><p><a href="/materials?${query()}" target="_blank" rel="noopener">${l.json}</a> · <a href="/output?${query()}" target="_blank" rel="noopener">${l.output}</a></p>${cue?`<p>${l.time}: ${tm(cue.show_at)}–${tm(cue.remove_at)} · ${esc(cue.material_id)}</p><details><summary>JSON · ${esc(cue.schema_version)}</summary><pre>${esc(JSON.stringify(cue,null,2))}</pre></details>`:''}`;
    if(wasOpen&&detail.querySelector('details'))detail.querySelector('details').open=true;
  }
  function visible(el){if(document.hidden||!el||el.hidden)return false;const rect=el.getBoundingClientRect();return rect.width>0&&rect.height>0&&rect.bottom>0&&rect.top<innerHeight&&rect.right>0&&rect.left<innerWidth;}
  function attemptAck(){const d=data?.delivery,cue=active();if(!d||!cue||cue.material_id!==d.material_id||!visible($('live-material'))&&!visible($('overlay-story')))return;
    const key=data.run_key+':'+d.material_id+':'+d.revision;if(acked.has(key)||inflight.has(key)||(retryAt.get(key)||0)>performance.now())return;
    inflight.add(key);const runKey=data.run_key,receipt={...d},requestMs=request.requestMs||0,arrived=request.receivedAt||performance.now();
    requestAnimationFrame(()=>requestAnimationFrame(async()=>{try{
      if(data.run_key!==runKey||(active()?.material_id!==receipt.material_id||active()?.revision!==receipt.revision)||!visible($('live-material'))&&!visible($('overlay-story')))return;
      const response=await fetch('/presentation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_key:runKey,token:receipt.token,material_id:receipt.material_id,revision:receipt.revision,event_id:receipt.event_id,render_ms:Math.max(0,performance.now()-arrived),request_ms:requestMs,visible:true})});
      if(response.ok)acked.add(key);else retryAt.set(key,performance.now()+1000);
    }catch{retryAt.set(key,performance.now()+1000);}finally{inflight.delete(key);}}));
  }
  window.EHStory={update(next,_focus,timing){if(!next)return;data=next;focus=next.focus;request=timing;received=performance.now();if(run!==data.run_key){run=data.run_key;acked=new Set();inflight=new Set();retryAt=new Map();periodKey='';cardKey='';}renderCard();renderPeriod();renderFocus();renderHealth();},focus:()=>focus,refresh(){if(data){renderCard();renderPeriod();renderFocus();}}};
  const observer=new IntersectionObserver(()=>attemptAck(),{threshold:.1});observer.observe($('live-material'));observer.observe($('overlay-story'));
  document.addEventListener('visibilitychange',()=>attemptAck());
  function tick(){if(data)renderCard();requestAnimationFrame(tick);}requestAnimationFrame(tick);
})();
