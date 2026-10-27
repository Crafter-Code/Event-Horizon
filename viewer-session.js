(() => {
  if(location.pathname==='/editor'||new URLSearchParams(location.search).get('shared')==='1')return;
  const nativeFetch=window.fetch.bind(window);
  const paths=new Set(['/state','/event','/runs','/materials','/generator','/vision','/video/frame.png','/agent-trace','/operations','/journey/state','/story-language','/language-proof','/displayed','/presentation','/viewer-session/start','/viewer-session/release']);
  let token=null,initializing=null,started=false;
  function scoped(url){return url.origin===location.origin&&paths.has(url.pathname);}
  window.fetch=(input,options)=>{
    const request=new Request(input,options),url=new URL(request.url);
    if(token&&scoped(url)){
      const headers=new Headers(request.headers);headers.set('X-EH-Viewer-Session',token);
      return nativeFetch(new Request(request,{headers}));
    }
    return nativeFetch(request);
  };
  async function ensure(){
    if(token)return;
    if(!initializing)initializing=(async()=>{
      const response=await nativeFetch('/viewer-session',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
      if(!response.ok){const error=Error(response.status===429?'A personal match is already in use. Waiting for a free slot…':'Preparing your personal match. Retrying…');error.viewerPending=true;throw error;}
      const data=await response.json();token=data.token;started=false;
    })().finally(()=>{initializing=null;});
    return initializing;
  }
  async function start(){
    if(started)return;
    const overlay=document.getElementById('kickoff-overlay'),main=document.querySelector('main');
    const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
    const previous=document.body.style.overflow;
    if(overlay){main.inert=true;document.body.style.overflow='hidden';overlay.hidden=false;
      try{await new Promise(resolve=>setTimeout(resolve,reduced?200:1400));overlay.classList.add('is-leaving');await new Promise(resolve=>setTimeout(resolve,reduced?0:300));}
      finally{overlay.hidden=true;overlay.classList.remove('is-leaving');main.inert=false;document.body.style.overflow=previous;}}
    const response=await fetch('/viewer-session/start',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
    if(!response.ok)throw Error('Personal match could not start');
    started=true;
  }
  function reset(){token=null;started=false;}
  function scopeLinks(){if(!token)return;for(const link of document.querySelectorAll('a[href]')){
    const url=new URL(link.href,location.href);if(scoped(url)&&link.target==='_blank'&&url.searchParams.get('viewer_session')!==token){url.searchParams.set('viewer_session',token);link.href=url.href;}
  }}
  new MutationObserver(scopeLinks).observe(document.body,{childList:true,subtree:true});
  window.addEventListener('pagehide',()=>{if(token)fetch('/viewer-session/release',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true}).catch(()=>{});});
  window.addEventListener('pageshow',event=>{if(event.persisted)reset();});
  window.EHViewerSession={ensure,start,reset};
})();
