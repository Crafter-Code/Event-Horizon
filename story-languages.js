                                                                                  
(function(root){
  const languages={en:'English',cs:'Čeština',de:'Deutsch',fr:'Français',it:'Italiano',es:'Español',pt:'Português'};
  const copy={
    en:{title:'One match · seven explanation languages',language:'Explanation language',intro:'Choose the language of the story. The interface keeps your current language.',loading:'Preparing the source-based explanation…',waiting:'An explanation appears when a recorded episode is available.',held:'The explanation is withheld because its source checks did not pass.',error:'The explanation could not be loaded. Try again.',retry:'Try again',what:'What happened',why:'Why it matters',change:'How the game changes',personal:'Your perspective',caption:'On-screen wording',recap:'Match recap',source:'Source event',sources:'Supporting events',basis:'Source-based explanation · facts and references preserved',json:'Inspect this translation',saved:'This explanation language is saved in your browser.',notSaved:'The explanation language could not be saved in this browser.'},
    cs:{title:'Jeden zápas · sedm jazyků vysvětlení',language:'Jazyk vysvětlení',intro:'Zvolte jazyk příběhu. Rozhraní si ponechá váš současný jazyk.',loading:'Připravujeme vysvětlení ze zdrojových událostí…',waiting:'Vysvětlení se zobrazí, jakmile je dostupná zaznamenaná epizoda.',held:'Vysvětlení je pozastaveno, protože neprošlo kontrolou zdrojů.',error:'Vysvětlení se nepodařilo načíst. Zkuste to znovu.',retry:'Zkusit znovu',what:'Co se stalo',why:'Proč je to důležité',change:'Jak se hra mění',personal:'Váš pohled',caption:'Text do obrazu',recap:'Souhrn zápasu',source:'Zdrojová událost',sources:'Podkladové události',basis:'Vysvětlení ze zdrojů · fakta a odkazy zachovány',json:'Prohlédnout tento překlad',saved:'Jazyk vysvětlení je uložen v tomto prohlížeči.',notSaved:'Jazyk vysvětlení se nepodařilo uložit v tomto prohlížeči.'},
    de:{title:'Ein Spiel · sieben Erklärungssprachen',language:'Sprache der Erklärung',intro:'Wählen Sie die Sprache der Geschichte. Die Oberfläche behält Ihre aktuelle Sprache.',loading:'Die quellenbasierte Erklärung wird vorbereitet…',waiting:'Eine Erklärung erscheint, sobald eine aufgezeichnete Szene verfügbar ist.',held:'Die Erklärung wird zurückgehalten, weil ihre Quellenprüfung fehlgeschlagen ist.',error:'Die Erklärung konnte nicht geladen werden. Bitte erneut versuchen.',retry:'Erneut versuchen',what:'Was passiert ist',why:'Warum es wichtig ist',change:'Wie sich das Spiel verändert',personal:'Ihre Perspektive',caption:'Text für die Einblendung',recap:'Spielzusammenfassung',source:'Quellereignis',sources:'Zugrunde liegende Ereignisse',basis:'Quellenbasierte Erklärung · Fakten und Verweise erhalten',json:'Diese Übersetzung prüfen',saved:'Diese Erklärungssprache ist in Ihrem Browser gespeichert.',notSaved:'Die Erklärungssprache konnte in diesem Browser nicht gespeichert werden.'}
  };
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clock=t=>`${String(Math.floor(t/60)).padStart(2,'0')}:${String(Math.floor(t%60)).padStart(2,'0')}`;
  let state=null,selected='en',element=null,lastKey='',controller=null,sequence=0,storageOk=true;
  function chosen(storage,fallback='en'){try{const value=storage.getItem('event-horizon-story-language');return Object.hasOwn(languages,value)?value:fallback;}catch{return fallback;}}
  function markup(result,uiLanguage='en',source='live'){
    const baseCopy=copy[globalThis.EHLocale?.base(uiLanguage)??uiLanguage]||copy.en;
    const l=Object.fromEntries(Object.entries(baseCopy).map(([key,text])=>[key,globalThis.EHLocale?.t(text,uiLanguage)||text]));
    if(result.status!=='ready'&&!result.recap)return `<p class="story-language-state">${esc(result.status==='held'?l.held:l.waiting)}</p>`;
    const e=result.episode,path=source==='demo'?'/demo/event':'/event';
    const ids=[...new Set([...(e?.source_event_ids||[]),...(result.recap?.source_event_ids||[])])].filter(n=>Number.isSafeInteger(n)&&n>0);
    const examples=ids.length<=12?ids:[...ids.slice(0,4),...ids.slice(-8)];
    const links=examples.map(id=>`<a href="${path}?${new URLSearchParams({id,run_key:result.run_key,language:uiLanguage})}" target="_blank" rel="noopener" aria-label="${esc(l.source)} #${id}">#${id} ↗</a>`).join('');
    const prose=e?`<article class="story-language-prose" lang="${esc(result.language)}" data-audience="${esc(result.audience)}" data-fingerprint="${esc(e.fact_fingerprint)}"><div class="story-language-meta">${clock(e.time)} · ${esc(languages[result.language])}</div><h3>${esc(e.title)}</h3>${[['what',e.what],['why',e.why],['change',e.change],['personal',e.personal]].map(([key,text])=>`<section><h4 lang="${esc(uiLanguage)}">${esc(l[key])}</h4><p>${esc(text)}</p></section>`).join('')}<details><summary lang="${esc(uiLanguage)}">${esc(l.caption)}</summary><p class="story-language-caption">${esc(e.caption)}</p></details></article>`:'';
    const recap=result.recap?`<section class="story-language-recap" lang="${esc(result.language)}"><h3>${esc(result.recap.title||l.recap)}</h3><p>${esc(result.recap.text)}</p>${result.recap.goals?.length?`<ol>${result.recap.goals.map(g=>`<li>${clock(g.time)} · ${g.score.map(n=>Number(n)).join(' : ')}</li>`).join('')}</ol>`:''}</section>`:'';
    return prose+recap+`<div class="story-language-basis">${esc(l.basis)}</div><details><summary>${esc(l.sources)} · ${ids.length}</summary><div class="story-language-sources">${links}</div><p class="story-language-hash">${esc(e?.protected_sha256||result.recap?.fact_fingerprint||'')}</p></details>`;
  }
  function setup(){
    if(element)return;
    element=document.getElementById('explanation-languages');
    if(!element)return;
    try{selected=chosen(localStorage,state?.uiLanguage||root.EHPreferences?.load(localStorage)?.language||'en');}catch{selected=state?.uiLanguage||'en';storageOk=false;}
    element.innerHTML='<summary class="story-language-heading"></summary><div class="story-language-controls"><label for="explanation-language"></label><select id="explanation-language"></select><p class="story-language-intro"></p></div><div class="story-language-body" aria-live="polite"></div><p class="story-language-storage"></p>';
    element.querySelector('select').innerHTML=Object.entries(languages).map(([code,name])=>`<option value="${code}">${esc(name)}</option>`).join('');
    element.querySelector('select').value=selected;
    element.querySelector('select').onchange=()=>{
      selected=element.querySelector('select').value;
      try{localStorage.setItem('event-horizon-story-language',selected);storageOk=true;}catch{storageOk=false;}
      lastKey='';refresh();
    };
    element.ontoggle=()=>{if(element.open)refresh();else{controller?.abort();lastKey='';}};
  }
  async function refresh(){
    if(!state)return;setup();if(!element)return;
    const l=copy[globalThis.EHLocale?.base(state.uiLanguage)??state.uiLanguage]||copy.en;
    element.querySelector('.story-language-heading').textContent=l.title;
    element.querySelector('label').textContent=l.language;
    element.querySelector('.story-language-intro').textContent=l.intro;
    element.querySelector('.story-language-storage').textContent=storageOk?l.saved:l.notSaved;
    if(!element.open)return;
    const key=JSON.stringify([state.source,state.runKey,state.episode,state.revision,state.fingerprint,selected,state.uiLanguage,state.audience,state.team,state.player,state.clock>=5400,state.episode?null:Math.floor(state.clock)]);
    if(key===lastKey)return;lastKey=key;
    controller?.abort();controller=new AbortController();const request=++sequence,snapshot={...state};
    const body=element.querySelector('.story-language-body');body.textContent=l.loading;
    const query=new URLSearchParams({source:state.source,language:selected,audience:state.audience,team:state.team??'all',player:state.player||'none',run_key:state.runKey});
    if(state.source==='demo')query.set('at',state.clock);
    if(state.episode)query.set('episode',state.episode);
    if(state.fingerprint)query.set('fingerprint',state.fingerprint);
    try{
      const response=await fetch('/story-language?'+query,{cache:'no-store',signal:controller.signal});
      if(!response.ok)throw Error('Story unavailable');const result=await response.json();
      if(request!==sequence||result.run_key!==snapshot.runKey||!element.open)return;
      body.innerHTML=markup(result,snapshot.uiLanguage,snapshot.source);
    }catch(error){if(error.name==='AbortError'||request!==sequence)return;body.innerHTML=`<p>${esc(l.error)}</p><button class="story-language-retry">${esc(l.retry)}</button>`;body.querySelector('button').onclick=()=>{lastKey='';refresh();};}
  }
  const api={languages,chosen,markup,
    live(experience,prefs){
      if(!experience)return;
      const e=experience.selected;
      const same=experience.scene_unchanged&&state?.source==='live'&&state.runKey===experience.run_key;
      state={source:'live',runKey:experience.run_key,clock:experience.clock??experience.context?.current?.end??0,uiLanguage:prefs.language,audience:prefs.audience,team:prefs.team,player:prefs.player,
        episode:e?.id||(same?state.episode:null),revision:e?.revision||(same?state.revision:null),fingerprint:e?.fact_fingerprint||(same?state.fingerprint:null)};
      refresh();
    },
    archived(data,prefs){
      const e=data.episode;
      state={source:'demo',runKey:data.run_key,clock:data.clock,uiLanguage:prefs.language,audience:prefs.audience,team:prefs.team,player:prefs.player,
        episode:e?.id||null,revision:e?.revision||null,fingerprint:e?.fact_fingerprint||null};refresh();
    }
  };
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else {root.EHExplanationLanguages=api;setup();}
})(typeof window!=='undefined'?window:this);
