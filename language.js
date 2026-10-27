                                                                               
(() => {
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const copy={

    de:{"title":"Eine Szene · drei Sprachen","intro":"Die Formulierung ändert sich; die Quellen bleiben dieselben.","pass":"Fakten, Zahlen, Namen und Quellen erhalten","fail":"Eine Abweichung wurde erkannt","wait":"Wählen Sie eine Szene zum Sprachvergleich.","loading":"Drei Sprachfassungen werden geprüft…","error":"Der Sprachvergleich konnte nicht geladen werden.","what":"Was passiert ist","why":"Warum es wichtig ist","change":"Wie sich das Spiel verändert","caption":"Einblender","sources":"Quellen","names":"Beteiligte","facts":"Gemeinsamer Fakten-Fingerabdruck","fan":"Kurz · Fan","analyst":"Ausführlich · Analyst","player":"Spielerfokus"},
    en:{title:'One episode · three languages',intro:'The wording changes; the sources stay shared.',pass:'Facts, numbers, names and sources preserved',fail:'A mismatch was detected',wait:'Select an episode to compare languages.',loading:'Checking three language versions…',error:'Could not load the language comparison.',what:'What happened',why:'Why it matters',change:'How the game changes',caption:'On-screen caption',sources:'Sources',names:'Participants',facts:'Shared facts fingerprint',fan:'Concise · Fan',analyst:'Detailed · Analyst',player:'Player Focus'},
    cs:{title:'Jedna epizoda · tři jazyky',intro:'Formulace se mění; zdroje zůstávají společné.',pass:'Fakta, čísla, jména a zdroje zachovány',fail:'Byl zjištěn nesoulad',wait:'Pro porovnání jazyků vyberte epizodu.',loading:'Ověřujeme tři jazykové verze…',error:'Porovnání jazyků se nepodařilo načíst.',what:'Co se stalo',why:'Proč je to důležité',change:'Jak se hra mění',caption:'Titulek do obrazu',sources:'Zdroje',names:'Účastníci',facts:'Společný otisk faktů',fan:'Stručně · Fan',analyst:'Podrobně · Analyst',player:'Vybraný hráč'}
  };
  const root=document.createElement('details');root.id='language-proof';root.className='language-proof';root.dataset.localized='true';
  root.innerHTML='<summary id="language-proof-heading"></summary><div id="language-proof-body"></div>';
  document.getElementById('why-body').after(root);
  let state=null,key='',result=null,pending=0,displayKey='',loadingKey='';
  function render(){
    if(!state)return;const l=copy[globalThis.EHLocale?.base(state.language)??state.language],body=document.getElementById('language-proof-body');
    document.getElementById('language-proof-heading').textContent=l.title;
    if(!root.open)return;
    const version=key+state.language+(result?'ready':'loading');if(displayKey===version)return;displayKey=version;
    if(!state.selected){body.innerHTML=`<p>${l.wait}</p>`;return;}
    if(!result){body.innerHTML=`<p>${l.loading}</p>`;return;}
    const first=result.views[0].protected;
    body.innerHTML=`<p class="note">${l.intro} · ${l[state.audience]}</p><div class="language-integrity ${result.parity.status==='passed'?'ok':'failed'}">${result.parity.status==='passed'?l.pass:l.fail}</div><div class="language-versions">${result.views.map(v=>`<article lang="${v.language}" class="language-version"><span class="section-label">${({de:'Deutsch',en:'English',cs:'Čeština'})[globalThis.EHLocale?.base(v.language)??v.language]}</span><h3>${esc(v.title)}</h3><p>${esc(v.what)}</p><p>${esc(v.why)}</p><p class="note">${esc(v.change)}</p><div class="caption-sample">${esc(v.caption)}</div></article>`).join('')}</div><p class="note">${l.names}: ${first.names.map(p=>`${esc(p.name)} (#${p.number})`).join(' · ')}</p><div class="source-links">${l.sources}: ${first.sources.map(s=>`<a href="${esc(s.href)}" target="_blank" rel="noopener">#${s.event_id}</a>`).join(' ')}</div><p class="note">${l.facts}: <code>${esc(result.views[0].facts_sha256.slice(0,16))}</code></p>`;
  }
  async function load(){
    if(!root.open||!state?.selected||result||loadingKey===key)return;
    loadingKey=key;
    const request=++pending,current=key,lang=state.language;
    try{const query=new URLSearchParams({episode:state.selected.id,audience:state.audience,run_key:state.run_key});const response=await fetch('/language-proof?'+query,{cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();if(request!==pending||current!==key)return;result=data;displayKey='';render();}
    catch{if(request===pending&&current===key){document.getElementById('language-proof-body').textContent=copy[globalThis.EHLocale?.base(lang)??lang].error;displayKey='';}}
    finally{if(request===pending)loadingKey='';}
  }
  root.ontoggle=()=>{displayKey='';render();load();};
  window.EHLanguage={update(next){state=next;const p=next.selected,newKey=[next.run_key,p?.id,p?.revision,next.audience].join(':');if(key!==newKey){key=newKey;result=null;pending++;displayKey='';loadingKey='';}render();load();}};
})();
