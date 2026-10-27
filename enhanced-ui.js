                                                                                        
(()=>{
 const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const t=s=>window.EHLocale?.t(s)||s;
 const help=(title,text)=>{const d=document.createElement('details');d.className='section-help';d.innerHTML=`<summary aria-label="${esc('About this section')}: ${esc(title)}"><span aria-hidden="true">i</span></summary><p role="note">${esc(text)}</p>`;return d;};
 const chapters=[
 ['One match, understood','Choose your view, then explore the evidence behind every story.'],
 ['Live match & statistics','Follow the same match clock, players and confirmed statistics. Choose where the short story appears.'],
 ['Reproduce the match','The same seed and scenario reproduce the same events. Replay Lab compares two independent runs.'],
 ['Key moments & review','Explore automatically identified episodes. The broadcast desk lets an editor check and select material.'],
 ['From event to insight','Open a completed pass to see its distance, direction, source events and automatic processing.'],
 ['One episode, three formats','The studio, broadcast and streaming views share the same source facts, with different levels of detail.'],
 ['Five connected stages','Receive an event, calculate its context, explain its significance, display it and adapt it to the viewer.'],
 ['Made for your perspective','Choose the statistics you care about. Compare periods and follow the actual contribution of your selected player.'],
 ['Players, patterns & performance','Inspect player identification, pass quality, speed, changes in play and sourced match reports.'],
 ['Synthetic match laboratory','Explore the generator, scenarios and consistency checks. Recognition is evaluated separately against the source.'],
 ['One match, seven languages','The main Language control applies across the project. This comparison lets you inspect another explanation language.'],
 ['Compare the same facts','Compare several languages and viewing modes while keeping numbers, players and source references unchanged.'],
 ['Azure & trustworthy AI','Check the origin of the match, verified AI results, factual fallback and measured delivery latency.'],
 ['The complete match','Watch all 90 minutes of the verified synthetic replay, inspect episodes and open your personalized final summary.']
 ];
 const infoCopy={
 'Your match':'Choose how much detail to see, your language, team and player. Changes keep the same underlying football facts.',
 'Match statistics':'Confirmed team statistics from the event stream. These stay available when AI narration is unavailable.',
 'Why this moment?':'Inspect the entire event sequence. Arrows show recorded passes; source links explain each claim.',
 'Statistics on screen':'Select which metrics appear in the match, charts and personalized cards. Your choices are saved in this browser.'
 };
 let main=$('main.eh-live'),frames=null,feedback=null,pending=false,changeId=0,lastFormats='';
 function addInfo(element,title,text){if(!element||element.querySelector(':scope > .section-help'))return;element.classList.add('has-section-help');if(element.matches('.global-preferences'))element.prepend(help(title,text));else element.append(help(title,text));}
 function move(parent,selector){const e=$(selector);if(e)parent.append(e);return e;}
 if(main){
   const footer=main.querySelector('footer'),sections=[];
   for(let i=0;i<14;i++){const section=document.createElement('section');section.className='eh-chapter';section.id='chapter-'+String(i+1).padStart(2,'0');section.dataset.chapter=i+1;
    const header=document.createElement('div');header.className='chapter-heading';header.innerHTML=`<span class="chapter-number" aria-hidden="true">${String(i+1).padStart(2,'0')}</span><h2>${esc(chapters[i][0])}</h2>`;header.append(help(chapters[i][0],chapters[i][1]));section.append(header);main.insertBefore(section,footer);sections.push(section);}
   const hero=document.createElement('div');hero.className='experience-intro';hero.innerHTML='<div class="section-label">EVENT HORIZON · AI MATCH INTELLIGENCE</div><h2>Watch the match. Understand the moment.</h2><p>Choose your view, then explore the evidence behind every story.</p>';sections[0].append(hero);
   move(sections[0],'.workspace-toolbar');move(sections[0],'.global-preferences');
   for(const s of ['.scoreboard','#connection','.layout','#pipeline-error'])move(sections[1],s);
   const identity=document.createElement('div');identity.id='pitch-identity-strip';identity.className='pitch-identity-strip';sections[1].append(identity);
   move(sections[2],'.session-settings');const repro=document.createElement('div');repro.className='chapter-note';repro.innerHTML='<p>The same seed and scenario reproduce the same events. Replay Lab compares two independent runs.</p><a class="chapter-action" href="/replay-lab">Replay Lab ↗</a>';sections[2].append(repro);
   move(sections[3],'#fan-view');move(sections[3],'#editor-view');move(sections[4],'.pass-platform');
   const formats=document.createElement('div');formats.id='audience-format-preview';formats.className='audience-format-preview';sections[5].append(formats);
   move(sections[6],'#experience');
   for(const s of ['.metric-settings','#continuous-focus','#period-comparison','.context-grid','#context-story','#player-focus','.pulse','.stream-heading','#key-moments','#no-moments'])move(sections[7],s);
   for(const s of ['#video-analysis','#live-rhythm','#match-report'])move(sections[8],s);
   move(sections[9],'#scenario-lab');move(sections[10],'#explanation-languages');move(sections[11],'#language-proof');
   for(const s of ['#intelligence-provenance','#delivery-health','#latency-strip'])move(sections[12],s);
   const finale=document.createElement('div');finale.className='complete-match-card';finale.innerHTML='<div><div class="section-label">90:00 · SYNTHETIC MATCH</div><h3>90 minutes. Every conclusion can be checked.</h3><p>Watch the full replay, compare viewing modes and open the final summary.</p></div><a class="chapter-action" href="/demo">Open full replay ↗</a>';sections[13].append(finale);
   const nav=document.createElement('nav');nav.className='chapter-navigation';nav.setAttribute('aria-label','Explore all 14 sections');nav.innerHTML=chapters.map((c,i)=>`<a href="#chapter-${String(i+1).padStart(2,'0')}" aria-label="${i+1}. ${esc(c[0])}" title="${esc(c[0])}">${String(i+1).padStart(2,'0')}</a>`).join('');$('.eh-live > header').after(nav);
   const metricSettings=$('.metric-settings');if(metricSettings){const wrap=document.createElement('div');wrap.className='metric-settings-help';metricSettings.before(wrap);wrap.append(metricSettings);addInfo(wrap,'Statistics on screen',infoCopy['Statistics on screen']);}
   addInfo($('.global-preferences'),'Your match',infoCopy['Your match']);addInfo($('#panel'),'Match statistics',infoCopy['Match statistics']);
                                                                                
   const updateRole=()=>{for(const selector of ['.pulse','.stream-heading','#key-moments','#no-moments']){const e=$(selector);if(e)e.classList.toggle('viewer-only-hidden',!!$('#fan-view')?.hidden);}};
   new MutationObserver(updateRole).observe($('#fan-view'),{attributes:true,attributeFilter:['hidden']});updateRole();
 }
 const preferenceBox=$('.global-preferences')||$('.toolbar.needs-ready');
 if(!main){addInfo(preferenceBox,'Your match',infoCopy['Your match']);}
 if(preferenceBox){feedback=document.createElement('div');feedback.className='preference-feedback';feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');feedback.setAttribute('aria-atomic','true');feedback.innerHTML='<span class="preference-state-dot" aria-hidden="true"></span><span class="preference-feedback-copy">Choices are saved in this browser.</span>';preferenceBox.after(feedback);}
 function selectedFields(){return ['#viewer-mode','#language','#favorite-team','#favorite-player','#demo-mode','#demo-language','#demo-team','#demo-player'].map(s=>$(s)).filter(Boolean);}
 function labelSummary(){return selectedFields().map(s=>s.selectedOptions?.[0]?.textContent).filter(Boolean).join(' · ');}
 function feedbackContent(state){
  if(!feedback)return;const fields=selectedFields(),mode=fields.find(s=>s.id==='viewer-mode'||s.id==='demo-mode')?.value||'fan';
  const descriptions={fan:'Short explanations and key moments, with your favourite team first.',analyst:'Detailed metrics, period comparisons and evidence behind each moment.',player:'Follow your selected player’s passes, shots and involvement throughout the match.'};
  const heading=state==='updating'?'Updating your experience…':state==='applied'?'Settings applied':'Choices are saved in this browser.';
  feedback.dataset.state=state;feedback.dataset.selection=labelSummary();
  feedback.innerHTML=`<span class="preference-state-dot" aria-hidden="true">${state==='updating'?'…':state==='applied'?'✓':'i'}</span><div class="preference-feedback-copy"><strong>${esc(t(heading))}</strong><p>${esc(t(descriptions[mode]))}</p><div class="preference-selection">${fields.map(s=>`<span class="selection-chip ${s.id.includes('team')?'selection-team-'+s.value:''}">${esc(s.selectedOptions?.[0]?.textContent||'')}</span>`).join('')}</div></div>`;
 }
 let confirmedTimer;
 document.addEventListener('change',event=>{
  if(!event.target.matches('#viewer-mode,#language,#favorite-team,#favorite-player,#demo-mode,#demo-language,#demo-team,#demo-player'))return;
  if(event.target.matches('#language,#demo-language'))window.EHLocale.apply(event.target.value);
  pending=true;changeId++;preferenceBox?.setAttribute('aria-busy','true');feedbackContent('updating');
  for(const e of document.querySelectorAll('.preference-changed'))e.classList.remove('preference-changed');event.target.closest('label')?.classList.add('preference-changed');
  document.body.dataset.preferenceChange=changeId;
 },true);
 function confirmed(){if(!pending){if(feedback&&feedback.dataset.selection!==labelSummary())feedbackContent(feedback.dataset.state||'idle');return;}pending=false;preferenceBox?.setAttribute('aria-busy','false');feedbackContent('applied');
  preferenceBox?.classList.remove('settings-confirmed');requestAnimationFrame(()=>preferenceBox?.classList.add('settings-confirmed'));
  clearTimeout(confirmedTimer);confirmedTimer=setTimeout(()=>{preferenceBox?.classList.remove('settings-confirmed');for(const e of document.querySelectorAll('.preference-changed'))e.classList.remove('preference-changed');},2600);
 }
 feedbackContent('idle');
 window.addEventListener('eh:preferences-applied',confirmed);
 window.addEventListener('eh:frame',event=>{frames=event.detail;confirmed();renderFormats();renderIdentity();});
 function renderFormats(){const node=$('#audience-format-preview');if(!node)return;const moment=frames?.insights?.moments?.[0],f=moment?.materials?.formats,key=moment?moment.id+':'+moment.revision+':'+window.EHLocale.language:'waiting:'+window.EHLocale.language;if(key===lastFormats)return;lastFormats=key;
 const labels=['Studio · presenter material','Broadcast · short caption','Streaming · personalized card'];node.innerHTML=labels.map((label,i)=>`<article><div class="format-index">0${i+1}</div><h3>${esc(t(label))}</h3><p>${esc(f?[f.studio.lead,f.broadcast.text,f.stream.personal||f.stream.summary][i]:t('Waiting for the first key episode. Match context keeps updating.'))}</p>${moment?`<small>${esc(t('Shared fact fingerprint'))} · ${esc(moment.fact_fingerprint.slice(0,12))}</small>`:''}</article>`).join('');}
 function renderIdentity(){const node=$('#pitch-identity-strip'),o=window.EHField?.lastObservation,prefs=window.EHSettings?.();if(!node||!o||!prefs)return;const people=(o.players||[]).filter(p=>`${p.team}:${p.number}`===prefs.player||o.owner&&p.team===o.owner[0]&&p.number===o.owner[1]);const key=JSON.stringify([prefs.metrics,people.map(p=>[p.team,p.number,Math.round(p.distance_m||0),p.speed_mps])]);if(node.dataset.key===key)return;node.dataset.key=key;node.innerHTML=people.map(p=>`<div class="player-identity-card"><span class="jersey-number team-${p.team}">${p.number}</span><span><strong>${esc(p.name)}</strong><small>${prefs.metrics.includes('movement')&&p.distance_m!=null?Math.round(p.distance_m)+' m':''}${prefs.metrics.includes('movement')&&p.speed_mps!=null?' · '+p.speed_mps.toFixed(1)+' m/s':''}</small></span></div>`).join('');}
 setInterval(renderIdentity,500);renderFormats();
 if(!$('#language')&&!$('#demo-language')){const header=$('header')||$('main');if(header){const label=document.createElement('label');label.className='site-language-control';label.innerHTML='<span>Language</span><select data-global-language aria-label="Language">'+Object.entries(window.EHLocale.names).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')+'</select>';header.append(label);label.querySelector('select').value=window.EHLocale.language;label.querySelector('select').onchange=()=>location.reload();}}
 document.addEventListener('click',event=>{for(const d of document.querySelectorAll('.section-help[open]'))if(!d.contains(event.target))d.open=false;});document.addEventListener('keydown',event=>{if(event.key==='Escape')for(const d of document.querySelectorAll('.section-help[open]')){d.open=false;d.querySelector('summary').focus();}});
 window.EHLocale?.apply();
})();
