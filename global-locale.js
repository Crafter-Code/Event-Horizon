                                                                                           
(function(root){
  const packs=root.EH_LOCALES||{},supported=['en','cs','de','fr','it','es','pt'];
  const names={en:'English',cs:'Čeština',de:'Deutsch',fr:'Français',it:'Italiano',es:'Español',pt:'Português'};
  let language='en';try{language=JSON.parse(localStorage.getItem('event-horizon-fan')||'{}').language||'en';}catch{}
  if(!supported.includes(language))language='en';
  const escape=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'), sources=new WeakMap(), attrs=new WeakMap();
  const missing=new Set();let scheduled=false;
  const all={};for(const pack of Object.values(packs))for(const [en,value] of Object.entries(pack))if(value!==en)all[value]=en;

  const folds={};for(const [lang,pack] of Object.entries(packs)){folds[lang]={};for(const [k,v] of Object.entries(pack))if(!Object.hasOwn(folds[lang],k.toLowerCase()))folds[lang][k.toLowerCase()]=v;}
  const rules={};for(const [lang,pack] of Object.entries(packs))rules[lang]=new RegExp('(?<![\\p{L}\\p{N}_])(?:'+Object.keys(pack).sort((a,b)=>b.length-a.length).map(escape).join('|')+')(?![\\p{L}\\p{N}_])','giu');
  const templates={};for(const [lang,pack] of Object.entries(packs)){templates[lang]=[];for(const [source,target] of Object.entries(pack)){const fields=[...source.matchAll(/\{([A-Za-z_][A-Za-z_0-9]*)\}/g)];if(!fields.length)continue;let at=0,pattern='';for(const f of fields){pattern+=escape(source.slice(at,f.index))+'((?:(?!\\. |\\n).)*?)';at=f.index+f[0].length;}pattern+=escape(source.slice(at));templates[lang].push({regex:new RegExp('^'+pattern+'$','iu'),fields:fields.map(f=>f[1]),target,size:source.length});}templates[lang].sort((a,b)=>b.size-a.size);}
  const nativeWords={fr:/\b(?:ballon|équipe|séquence|réussies|joueur|faits|aperçu|résumé|pression|précédente)\b/iu,it:/\b(?:pallone|palla|squadra|passaggi|giocatore|punteggio|possesso|partita|riepilogo|precedente|fotogrammi|primo|secondo)\b/iu,es:/\b(?:balón|equipo|jugador|jugada|marcador|posesión|pases|partido|resumen|pantalla|anterior)\b/iu,pt:/\b(?:bola|equipa|jogador|lance|marcador|posse|jogo|resumo|ecrã|remates|anterior)\b/iu};
  const nativeValues={};for(const [lang,pack] of Object.entries(packs))nativeValues[lang]=new Set(Object.values(pack).map(s=>s.toLowerCase()));
  function canonical(text){return all[text]||text;}
  function translate(text,lang=language){if(typeof text!=='string'||/EVENT HORIZON/i.test(text)||!packs[lang])return text;const pack=packs[lang];if(nativeValues[lang].has(text.toLowerCase())||nativeWords[lang]?.test(text))return text;if(Object.hasOwn(pack,text))return pack[text];if(!text.includes('{'))for(const row of templates[lang]){const m=text.match(row.regex);if(m){const v=Object.fromEntries(row.fields.map((f,i)=>[f,t(m[i+1],lang)]));return row.target.replace(/\{([A-Za-z_][A-Za-z_0-9]*)\}/g,(_,k)=>v[k]);}}const out=text.replace(rules[lang],m=>m.toLowerCase()==='play'?m:(pack[m]||folds[lang][m.toLowerCase()]||m));if(out===text&&/[a-z]{4}/i.test(text)&&!/^([\d\W]+|[a-f0-9]{12,}|Max Rowan|Sam Arden)$/.test(text))missing.add(text);return out;}
  const translationCache=new Map();
  function t(text,lang=language){const key=lang+'\u0000'+text;if(translationCache.has(key))return translationCache.get(key);const out=translate(text,lang);if(translationCache.size>8192)translationCache.clear();translationCache.set(key,out);return out;}
  function apply(code=language){if(supported.includes(code))language=code;document.documentElement.lang=language;
    if(!document.body)return;
    const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node;
    while(node=walker.nextNode()){
      if(node.parentElement?.closest('script,style,pre,code,.brand,#language option,#demo-language option,#explanation-language option,#journey-language option,[data-global-language] option,.language-version,.lens-grid article,.story-language-prose,.story-language-recap,[data-source-original]'))continue;
      const current=node.nodeValue,old=sources.get(node),source=old&&old.last===current?old.source:canonical(current),out=t(source);
      sources.set(node,{source,last:out});if(current!==out)node.nodeValue=out;
    }
    for(const e of document.querySelectorAll('[aria-label],[title],[placeholder]')){
      if(e.closest('[data-source-original]'))continue;
      const old=attrs.get(e)||{};
      for(const key of ['aria-label','title','placeholder']){const current=e.getAttribute(key);if(current==null)continue;const saved=old[key],source=saved?.last===current?saved.source:canonical(current),out=t(source);old[key]={source,last:out};if(out!==current)e.setAttribute(key,out);}attrs.set(e,old);
    }
    for(const select of document.querySelectorAll('#language,#demo-language,#language-select,#journey-language,[data-global-language]')){
      for(const [code,name] of Object.entries(names))if(!select.querySelector('option[value="'+code+'"]'))select.add(new Option(name,code));
    }
  }
  const originalFetch=root.fetch.bind(root);
  root.fetch=function(input,options={}){let url;try{url=new URL(typeof input==='string'?input:input.url,location.href);}catch{return originalFetch(input,options);}
    if(url.origin===location.origin){const headers=new Headers(options.headers||(input instanceof Request?input.headers:undefined));headers.set('X-EH-Language',language);options={...options,headers};if(url.searchParams.has('language')&&!['/story-language','/language-proof','/demo/lenses'].includes(url.pathname)){url.searchParams.set('language',language);input=typeof input==='string'?url.href:new Request(url,input);}}
    return originalFetch(input,options);
  };
  root.EHLocale={t,apply,names,supported,missing,base:code=>['fr','it','es','pt'].includes(code)?'en':code,get language(){return language;}};
  function start(){apply();new MutationObserver(()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;apply();});}).observe(document.body,{childList:true,subtree:true,characterData:true});
    document.addEventListener('change',e=>{if(['language','demo-language','journey-language'].includes(e.target.id)||e.target.matches('[data-global-language]')){apply(e.target.value);try{const prefs=JSON.parse(localStorage.getItem('event-horizon-fan')||'{}');prefs.language=language;localStorage.setItem('event-horizon-fan',JSON.stringify(prefs));}catch{}}},true);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})(window);
