                                                                                 
(()=>{
  const query=new URLSearchParams(location.search),external=query.get('clock')==='external';query.delete('clock');query.set('limit','1');
  let feed=null,received=0,media=null,paintKey='';const acked=new Set();
  const $=id=>document.getElementById(id),esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  window.addEventListener('message',event=>{const m=event.data;if(!external||event.origin!==location.origin||event.source!==parent&&event.source!==opener||!m||m.type!=='eh-clock'||typeof m.time!=='number'||!Number.isFinite(m.time)||m.time<0||m.time>5400)return;
    if(feed&&(m.match_id!==feed.match_id||m.run_key!==feed.run_key))return;
    media={time:m.time,playing:m.playing===true,at:performance.now(),match_id:m.match_id,run_key:m.run_key};
  });
  function clock(){if(!feed)return null;if(external){if(!media||media.match_id!==feed.match_id||media.run_key!==feed.run_key||media.playing&&performance.now()-media.at>2000)return null;return media.time+(media.playing?(performance.now()-media.at)/1000:0);}return feed.match_clock+(performance.now()-received)/1000;}
  function render(){const now=clock();if(!feed||now===null||performance.now()-received>2000){$('caption').hidden=true;$('metrics').hidden=true;return;}
    const eligible=feed.overlays.filter(c=>c.schema_version==='eh-overlay-1'&&c.match_id===feed.match_id&&c.run_key===feed.run_key&&c.timebase.kind==='match_clock'&&c.show_at<=now&&now<c.remove_at);
    const caption=eligible.filter(c=>c.layer==='narrative').sort((a,b)=>b.priority-a.priority||b.show_at-a.show_at||b.revision-a.revision)[0];
    $('caption').hidden=!caption;if(caption){$('caption').dataset.materialId=caption.material_id;$('caption').dataset.revision=caption.revision;$('event').textContent=caption.text.event;$('significance').textContent=caption.text.significance;$('evidence').textContent=caption.text.evidence;}
    const stats=eligible.find(c=>c.layer==='statistics');$('metrics').hidden=!stats;if(stats)$('metrics').innerHTML=stats.metrics.map(m=>`<div class="row"><span>${esc(m.label)}</span><strong>${Array.isArray(m.value)?m.value.map(esc).join(' : '):esc(m.value)}${m.unit==='percent'?' %':''}</strong></div>`).join('');
    const d=feed.delivery,key=d&&feed.run_key+':'+d.material_id+':'+d.revision;
    if(!external&&caption&&!document.hidden&&d&&caption.material_id===d.material_id&&!acked.has(key)&&paintKey!==key){paintKey=key;const runKey=feed.run_key,arrived=received;requestAnimationFrame(()=>requestAnimationFrame(async()=>{try{if(document.hidden||feed.run_key!==runKey||$('caption').hidden||$('caption').dataset.materialId!==d.material_id||Number($('caption').dataset.revision)!==d.revision)return;const response=await fetch('/presentation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_key:runKey,token:d.token,material_id:d.material_id,revision:d.revision,event_id:d.event_id,visible:true,render_ms:Math.max(0,performance.now()-arrived),request_ms:feed.request_ms||0})});if(response.ok)acked.add(key);}catch{}finally{paintKey='';}}));}
  }
  async function poll(){try{const q=new URLSearchParams(query);if(external&&media)q.set('at',Math.min(5400,media.time+(media.playing?(performance.now()-media.at)/1000:0)).toFixed(2));const start=performance.now();const response=await fetch('/materials?'+q,{cache:'no-store',signal:AbortSignal.timeout(2000)});if(!response.ok)throw Error('Invalid material feed');const next=await response.json();next.request_ms=performance.now()-start;if(feed&&feed.run_key!==next.run_key){media=null;acked.clear();}feed=next;received=performance.now();document.documentElement.lang=query.get('language')||'en';}catch{}finally{setTimeout(poll,100);}}
  function frame(){render();requestAnimationFrame(frame);}poll();requestAnimationFrame(frame);
})();
