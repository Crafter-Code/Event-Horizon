                                                                                 
(function(root){
  const copy={
    en:{eyebrow:'Read the change',title:'The rhythm behind the moment',intro:'Two completed minutes. See what changed before deciding what it means.',
      waiting:'The comparison starts after two complete minutes of play.',previous:'Previous minute',current:'Latest completed minute',
      turnovers:'Possession changes',pass_starts:'Pass starts',shots:'Shots',pressure_blue:'Blue · pressure',pressure_red:'Red · pressure',
      more:'More',fewer:'Fewer',same:'Unchanged',turnoverRise:'Possession changed hands more often.',turnoverFall:'Possession changed hands less often.',turnoverSame:'The number of possession changes stayed the same.',
      explanation:'Changes of possession help reveal how often a spell of play was interrupted. They do not establish tactical intent.',
      context:'Match-level context. Individual player contributions remain in Player Focus.',method:'How to read this',
      scales:'Each row has its own scale. Green means the later minute; it does not mean better.',
      boundary:'Passes count starts. Pressure counts seconds with an opponent within 5 m of the ball, separately for each team. These are observed comparisons, not AI interpretations or a control score.',
      evidence:'Inspect the evidence',sample:'Source examples from both windows',all:'Counted source events',source:'Source event',seconds:'s',fingerprint:'Source fingerprint',unit:'events'},
    cs:{eyebrow:'Přečtěte změnu',title:'Rytmus za tímto okamžikem',intro:'Dvě dokončené minuty. Než posoudíte význam, podívejte se, co se změnilo.',
      waiting:'Porovnání začne po dvou celých minutách hry.',previous:'Předchozí minuta',current:'Poslední dokončená minuta',
      turnovers:'Změny držení míče',pass_starts:'Zahájené přihrávky',shots:'Střely',pressure_blue:'Modří · tlak',pressure_red:'Červení · tlak',
      more:'Více',fewer:'Méně',same:'Beze změny',turnoverRise:'Míč častěji měnil držení.',turnoverFall:'Míč méně často měnil držení.',turnoverSame:'Počet změn držení míče zůstal stejný.',
      explanation:'Změny držení ukazují, jak často bylo držení míče přerušeno. Neurčují taktický záměr.',
      context:'Kontext celého zápasu. Přínos jednotlivce zůstává v režimu Player Focus.',method:'Jak číst srovnání',
      scales:'Každý řádek má vlastní měřítko. Zelená označuje pozdější minutu; neznamená lepší výkon.',
      boundary:'Přihrávky počítají zahájení. Tlak měří sekundy se soupeřem do 5 m od míče, pro každý tým zvlášť. Jde o pozorovaná srovnání, nikoli interpretace AI nebo skóre kontroly hry.',
      evidence:'Prohlédnout podklady',sample:'Příklady zdrojů z obou úseků',all:'Započítané události',source:'Zdrojová událost',seconds:'s',fingerprint:'Otisk zdrojů',unit:'události'},
    de:{eyebrow:'Die Veränderung lesen',title:'Der Rhythmus hinter dem Moment',intro:'Zwei abgeschlossene Minuten. Erst die Veränderung ansehen, dann ihre Bedeutung beurteilen.',
      waiting:'Der Vergleich beginnt nach zwei vollständigen Spielminuten.',previous:'Vorherige Minute',current:'Letzte abgeschlossene Minute',
      turnovers:'Ballbesitzwechsel',pass_starts:'Begonnene Pässe',shots:'Schüsse',pressure_blue:'Blau · Druck',pressure_red:'Rot · Druck',
      more:'Mehr',fewer:'Weniger',same:'Unverändert',turnoverRise:'Der Ballbesitz wechselte häufiger.',turnoverFall:'Der Ballbesitz wechselte seltener.',turnoverSame:'Die Zahl der Ballbesitzwechsel blieb gleich.',
      explanation:'Ballbesitzwechsel zeigen, wie oft eine Ballbesitzphase unterbrochen wurde. Eine taktische Absicht ist damit nicht belegt.',
      context:'Kontext des gesamten Spiels. Einzelne Spielerbeiträge bleiben in Player Focus.',method:'So lesen Sie den Vergleich',
      scales:'Jede Zeile hat ihre eigene Skala. Grün bezeichnet die spätere Minute; es bedeutet nicht besser.',
      boundary:'Pässe zählen Anfänge. Druck zählt Sekunden mit einem Gegner innerhalb von 5 m um den Ball, getrennt nach Mannschaft. Dies sind beobachtete Vergleiche, keine KI-Interpretationen oder Kontrollwerte.',
      evidence:'Belege prüfen',sample:'Quellbeispiele aus beiden Zeiträumen',all:'Gezählte Quellereignisse',source:'Quellereignis',seconds:'s',fingerprint:'Quellfingerabdruck',unit:'Ereignisse'}
  };
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const time=n=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(Math.floor(n%60)).padStart(2,'0')}`;
  const finite=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0;
  function markup(data,options={}){
    const language=Object.hasOwn(copy,options.language)?options.language:'en',l=copy[globalThis.EHLocale?.base(language)??language];
    const head=`<div class="rhythm-kicker">${l.eyebrow}</div><h2>${l.title}</h2>`;
    if(data?.status!=='ready')return `${head}<p class="rhythm-intro">${l.waiting}</p>`;
    const selected=options.metrics||['possession','tempo','shots','pressure'];
    let rows=(data.rows||[]).filter(r=>selected.includes(r.preference)&&finite(r.previous)&&finite(r.current));
    const turnover=rows.find(r=>r.key==='turnovers');
    const story=turnover?(turnover.delta>0?l.turnoverRise:turnover.delta<0?l.turnoverFall:l.turnoverSame):l.intro;
    if(options.audience==='fan'){const simple=rows.filter(r=>r.key==='turnovers'||r.key==='shots');rows=(simple.length?simple:rows).slice(0,2);}
    const windows=data.windows;
    const range=w=>`${time(w.start)}–${time(w.end)}`;
    const number=n=>n.toLocaleString(language,{maximumFractionDigits:1});
    const rowHtml=rows.map(r=>{
      const ceiling=Math.max(r.previous,r.current,1),delta=r.current-r.previous;
      const unit=r.unit==='seconds'?` ${l.seconds}`:'';
      return `<div class="rhythm-row"><div class="rhythm-row-label">${esc(l[r.key]||r.key)}<span class="rhythm-delta">${delta>0?'+':''}${number(delta)}${unit}</span></div><div class="rhythm-bars" aria-hidden="true"><span class="rhythm-bar rhythm-bar--before" style="width:${r.previous/ceiling*100}%"></span><span class="rhythm-bar rhythm-bar--now" style="width:${r.current/ceiling*100}%"></span></div><div class="rhythm-values"><span>${l.previous}: <b>${number(r.previous)}${unit}</b></span><span>${l.current}: <b>${number(r.current)}${unit}</b></span></div></div>`;
    }).join('');
    const path=options.sourcePath==='/demo/event'?'/demo/event':'/event';
    const sources=[...new Set(data.source_event_ids||[])].filter(n=>Number.isSafeInteger(n)&&n>0).slice(0,12);
    const sourceHtml=sources.map(id=>`<a href="${path}?${new URLSearchParams({id,run_key:options.runKey||'',language})}" target="_blank" rel="noopener" aria-label="${l.source} #${id}">#${id} ↗</a>`).join('');
    return `${head}<p class="rhythm-lead">${esc(story)}</p><div class="rhythm-windows"><span><i class="rhythm-dot rhythm-dot--before"></i>${l.previous}<b>${range(windows.previous)}</b></span><span><i class="rhythm-dot"></i>${l.current}<b>${range(windows.current)}</b></span></div>${rowHtml?`<div class="rhythm-chart">${rowHtml}</div>`:''}${turnover?`<p class="rhythm-note">${l.explanation}</p>`:''}${options.audience==='player'?`<p class="rhythm-note">${l.context}</p>`:''}<details><summary>${l.method}</summary><p>${l.scales}</p><p>${l.boundary}</p></details><details><summary>${l.evidence} · ${Number(data.source_count)||0}</summary><p>${l.sample} · ${l.all}: ${Number(data.source_count)||0}</p><div class="rhythm-sources">${sourceHtml}</div><p class="rhythm-hash">${l.fingerprint}<br>${esc(data.source_fingerprint)}</p></details>`;
  }
  function update(element,data,options={}){
    if(!element)return;
    const selected=options.metrics;
    element.hidden=Array.isArray(selected)&&!selected.some(k=>['possession','tempo','shots','pressure'].includes(k));
    if(element.hidden)return;
    const key=JSON.stringify([data?.status==='ready'?data.source_fingerprint:'collecting',options]);
    if(element.dataset.rhythmKey===key)return;
    element.dataset.rhythmKey=key;
    const opened=[...element.querySelectorAll('details')].map(d=>d.open);
    element.innerHTML=markup(data,options);
    element.querySelectorAll('details').forEach((d,i)=>d.open=!!opened[i]);
    element.setAttribute('aria-label',(copy[globalThis.EHLocale?.base(options.language)??options.language]||copy.en).title);
  }
  const api={markup,update};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.EHRhythmLens=api;
})(typeof window!=='undefined'?window:this);
