                                                                                                     
(function(root){
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const colors=['#73ceff','#ff8998'];let serial=0;
                                                                                      
 function createMotion(clock=()=>performance.now()){
  let from=null,to=null,key=null,began=0,duration=160,lastArrival=0;
  const clone=o=>o?{...o,players:(o.players||[]).map(p=>({...p})),ball:Array.isArray(o.ball)?{x:o.ball[0],y:o.ball[1]}:o.ball?{...o.ball}:null}:null;
  function sample(at=clock()){
   if(!to)return null;if(!from||duration===0)return clone(to);
   const a=Math.max(0,Math.min(1,(at-began)/duration)),old=new Map((from.players||[]).map(p=>[p.team+':'+p.number,p]));
   const lerp=(x,y)=>x+(y-x)*a,dt=Math.max(.05,to.time-from.time);
   const players=(to.players||[]).map(p=>{const q=old.get(p.team+':'+p.number);return !q||Math.hypot(p.x-q.x,p.y-q.y)>dt*12+2?{...p}:{...p,x:lerp(q.x,p.x),y:lerp(q.y,p.y)};});
   let ball=to.ball?{...to.ball}:null;
   if(ball&&from.ball&&Math.hypot(ball.x-from.ball.x,ball.y-from.ball.y)<=dt*50+2)ball={...ball,x:lerp(from.ball.x,ball.x),y:lerp(from.ball.y,ball.y)};
   return {...to,time:lerp(from.time,to.time),players,ball};
  }
  function push(observation,identity,options={}){
   if(!observation||!Number.isFinite(observation.time))return;
   const now=clock(),reset=options.snap||!to||identity!==key||observation.time<to.time||observation.period!==to.period||observation.in_play!==to.in_play||observation.time-to.time>1||now-lastArrival>1500;
   if(!reset&&observation.frame_id===to.frame_id&&observation.time===to.time)return;
   from=reset?clone(observation):sample(now);to=clone(observation);key=identity;
   duration=reset?0:Math.max(90,Math.min(420,Math.max(now-lastArrival,duration*.9)*1.05));began=now;lastArrival=now;
  }
  return {push,sample,reset(){from=to=null;key=null;},get sourceTime(){return to?.time;}};
 }
 function routeGeometry(origin,end,padding=1.4){
  if(!Array.isArray(origin)||!Array.isArray(end)||origin.length!==2||end.length!==2||![...origin,...end].every(Number.isFinite))return null;
  if([origin,end].some(([x,y])=>x<0||x>105||y<0||y>68))return null;
  const [x,y]=origin,dx=end[0]-x,dy=end[1]-y,length=Math.hypot(dx,dy);if(length<.01)return null;
  const pad=Math.min(padding,length*.2),start=[x+dx/length*pad,y+dy/length*pad],finish=[end[0]-dx/length*pad,end[1]-dy/length*pad];
  return {origin:[...origin],end:[...end],start,finish,length,path:`M${start[0]} ${start[1]} L${finish[0]} ${finish[1]}`,ballPath:`M${x} ${y} L${end[0]} ${end[1]}`};
 }
 function passRoute(pass){
  const geometry=routeGeometry(pass.origin,pass.end);if(!geometry)return '';
  const event={frame:[{team:pass.team,number:pass.sender,x:pass.origin[0],y:pass.origin[1]},{team:pass.team,number:pass.receiver,x:pass.end[0],y:pass.end[1]}],ball:pass.origin};
  const e={kind:'pass_completed',team:pass.team,details:{origin:pass.origin,end:pass.end}};
  return svgScene(event,[e],{animate:true,loop:true,label:`Completed pass route #${pass.sender} to #${pass.receiver}`,endpointLabels:true,hideBall:true,focus:true});
 }
 function rounded(ctx,x,y,w,h,r){ctx.beginPath();ctx.roundRect(x,y,w,h,r);}
 function ground(ctx){
  const g=ctx.createLinearGradient(-8,-8,110,76);g.addColorStop(0,'#123c36');g.addColorStop(1,'#082b27');ctx.fillStyle=g;ctx.fillRect(-8,-8,121,84);
  ctx.fillStyle='#1c6048';ctx.fillRect(0,0,105,68);
  for(let i=0;i<10;i++){ctx.fillStyle=i%2?'#ffffff06':'#00000008';ctx.fillRect(i*10.5,0,10.5,68);}
  const glow=ctx.createRadialGradient(52.5,25,0,52.5,34,75);glow.addColorStop(0,'#72b28b14');glow.addColorStop(1,'#00000022');ctx.fillStyle=glow;ctx.fillRect(0,0,105,68);
  ctx.strokeStyle='#e4f2df99';ctx.lineWidth=.19;ctx.strokeRect(0,0,105,68);ctx.beginPath();ctx.moveTo(52.5,0);ctx.lineTo(52.5,68);ctx.stroke();ctx.beginPath();ctx.arc(52.5,34,9.15,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#e4f2df';ctx.beginPath();ctx.arc(52.5,34,.2,0,Math.PI*2);ctx.fill();
  for(const right of [false,true]){ctx.strokeRect(right?88.5:0,13.84,16.5,40.32);ctx.strokeRect(right?99.5:0,24.84,5.5,18.32);ctx.beginPath();ctx.arc(right?94:11,34,.18,0,7);ctx.fill();
   const x=right?105:-3;ctx.fillStyle='#071f20';ctx.fillRect(x,30.34,3,7.32);ctx.strokeStyle='#c5dfdc44';ctx.lineWidth=.07;for(let k=0;k<=6;k++){ctx.beginPath();ctx.moveTo(x+k*.5,30.34);ctx.lineTo(x+k*.5,37.66);ctx.stroke();}for(let y=30.34;y<37.67;y+=.61){ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+3,y);ctx.stroke();}ctx.strokeStyle='#f1f7f0';ctx.lineWidth=.25;ctx.strokeRect(x,30.34,3,7.32);ctx.strokeStyle='#e4f2df99';ctx.lineWidth=.19;
  }
 }
 function draw(ctx,canvas,o,prefs={},thresholds={speed:7,distance:1000}){
  if(!o)return false;const scale=Math.min(canvas.width/121,canvas.height/84),left=(canvas.width-105*scale)/2,top=(canvas.height-68*scale)/2;
  ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,canvas.width,canvas.height);ctx.setTransform(scale,0,0,scale,left,top);ground(ctx);
  const people=o.players||[],focus=prefs.player,owner=o.owner;const emphasized=[];
  for(const p of people){const chosen=focus===`${p.team}:${p.number}`,held=owner&&owner[0]===p.team&&owner[1]===p.number;
   ctx.fillStyle='#001c1d70';ctx.beginPath();ctx.ellipse(p.x+.16,p.y+.43,1.14,.68,0,0,7);ctx.fill();
   if(chosen||held){ctx.strokeStyle=chosen?'#d3f58b':'#ffffff70';ctx.lineWidth=.2;ctx.beginPath();ctx.arc(p.x,p.y,1.55,0,7);ctx.stroke();emphasized.push(p);}
   const fill=ctx.createLinearGradient(p.x,p.y-1,p.x,p.y+1);fill.addColorStop(0,p.team?'#ffb0b9':'#a1e2ff');fill.addColorStop(1,p.team?'#db566d':'#3ca1e3');ctx.fillStyle=fill;ctx.beginPath();ctx.arc(p.x,p.y,1.02,0,7);ctx.fill();ctx.strokeStyle='#ffffffbb';ctx.lineWidth=.13;ctx.stroke();
   ctx.fillStyle='#092431';ctx.font='700 1.07px system-ui';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(p.number,p.x,p.y+.03);
  }
  const b=Array.isArray(o.ball)?{x:o.ball[0],y:o.ball[1]}:o.ball;
  if(b){ctx.fillStyle='#00141688';ctx.beginPath();ctx.ellipse(b.x+.2,b.y+.25,.55,.32,0,0,7);ctx.fill();ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(b.x,b.y,.43,0,7);ctx.fill();ctx.strokeStyle='#153c37';ctx.lineWidth=.1;ctx.stroke();ctx.fillStyle='#315b52';ctx.beginPath();ctx.arc(b.x-.04,b.y-.02,.13,0,7);ctx.fill();}
  if(canvas.clientWidth>650){const used=[];for(const p of emphasized){let text=p.name||'#'+p.number;if(prefs.metrics?.includes('movement')&&p.speed_mps>=thresholds.speed)text+=' · '+p.speed_mps.toFixed(1)+' m/s';
    const size=12*canvas.width/Math.max(1,canvas.clientWidth)/scale;ctx.font=`600 ${size}px system-ui`;const w=Math.min(35,ctx.measureText(text).width+1.8),h=size+1.6,x=Math.max(-5,Math.min(110-w,p.x-w/2));let y=p.y-h-2;
    if(y< -5||used.some(r=>x<r.x+r.w&&x+w>r.x&&y<r.y+r.h&&y+h>r.y))y=p.y+2;
    used.push({x,y,w,h});ctx.fillStyle='#071e29ed';rounded(ctx,x,y,w,h,.65);ctx.fill();ctx.strokeStyle='#b6d1c82e';ctx.lineWidth=.1;ctx.stroke();ctx.fillStyle='#eef6f0';ctx.textAlign='center';ctx.fillText(text,x+w/2,y+h/2,w-1.4);
  }}
  ctx.setTransform(1,0,0,1,0,0);root.EHField.lastObservation=o;return true;
 }
 function svgScene(event,passes=[],options={}){
  const id='field-'+(++serial),reduced=typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  let box={x:-5,y:-6,width:115,height:80};
  if(options.focus&&passes[0]){const g=routeGeometry(passes[0].details?.origin,passes[0].details?.end);if(g){const a=g.origin,b=g.end,w=Math.min(115,Math.max(30,Math.abs(a[0]-b[0])+18,(Math.abs(a[1]-b[1])+18)*115/80)),h=w*80/115;box={x:Math.max(-5,Math.min(110-w,(a[0]+b[0]-w)/2)),y:Math.max(-6,Math.min(74-h,(a[1]+b[1]-h)/2)),width:w,height:h};}}
  const factor=box.width/115,stroke=options.endpointLabels ? .55*factor : .4;
  const routes=passes.map((e,i)=>{if(e.kind!=='pass_completed'||Number.isFinite(event.time)&&Number.isFinite(e.time)&&e.time>event.time)return '';const g=routeGeometry(e.details?.origin,e.details?.end,options.endpointLabels?2.6*factor:1.4);if(!g||![0,1].includes(e.team))return '';const color=colors[e.team],d=g.path;
   return `<g class="route-sequence" data-origin="${g.origin.join(',')}" data-end="${g.end.join(',')}"><path d="${d}" stroke="${color}" stroke-opacity=".12" stroke-width="${1.8*factor}" stroke-linecap="round" fill="none"/><path class="route-line" d="${d}" stroke="${color}" stroke-opacity="${.55+.4*(i+1)/Math.max(1,passes.length)}" stroke-width="${stroke}" stroke-linecap="round" fill="none" marker-end="url(#${id}-${e.team})"/>${!reduced&&options.animate!==false?`<circle class="route-ball" r="${.5*factor}" fill="#fff"><animateMotion dur="${options.loop?'2.4':'1.6'}s" begin="${i*.16}s" repeatCount="${options.loop?'indefinite':'1'}" fill="freeze" path="${g.ballPath}"/>${options.loop?'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.08;0.9;1" dur="2.4s" repeatCount="indefinite"/>':''}</circle>`:''}</g>`;}).join('');
  const actors=options.actors?new Set(options.actors.map(p=>`${p.team}:${p.number}`)):null;
  const players=(event.frame||event.players||[]).map(p=>{const active=!actors||actors.has(`${p.team}:${p.number}`);return `<g opacity="${active?1:.38}"><ellipse cx="${p.x+.12}" cy="${p.y+.35}" rx="1.1" ry=".6" fill="#001e2670"/><circle cx="${p.x}" cy="${p.y}" r="${options.endpointLabels?2.2*factor:1.08}" fill="${colors[p.team]}" stroke="#f4fbef" stroke-width=".13"/><text x="${p.x}" y="${p.y+(options.endpointLabels ? .95*factor : .42)}" text-anchor="middle" fill="#092733" font-size="${options.endpointLabels?2.9*factor:1.25}" font-family="system-ui" font-weight="700">${p.number}</text></g>`;}).join('');
  let overview='';if(options.focus&&passes[0]){const a=passes[0].details.origin,b=passes[0].details.end,points=[a,b,[(a[0]+b[0])/2,(a[1]+b[1])/2]],w=box.width*.23,h=box.height*.23;
   const corners=[[box.x+box.width*.03,box.y+box.height*.03],[box.x+box.width-w-box.width*.03,box.y+box.height*.03],[box.x+box.width*.03,box.y+box.height-h-box.height*.03],[box.x+box.width-w-box.width*.03,box.y+box.height-h-box.height*.03]];
   const [x,y]=corners.sort((u,v)=>Math.min(...points.map(p=>Math.hypot(p[0]-v[0]-w/2,p[1]-v[1]-h/2)))-Math.min(...points.map(p=>Math.hypot(p[0]-u[0]-w/2,p[1]-u[1]-h/2))))[0];
   overview=`<svg class="pass-overview" x="${x}" y="${y}" width="${w}" height="${h}" viewBox="-5 -6 115 80" aria-hidden="true"><rect x="-5" y="-6" width="115" height="80" rx="5" fill="#092729ed" stroke="#d9ead075" stroke-width="1"/><g fill="none" stroke="#c1d8ce88" stroke-width=".8"><rect width="105" height="68"/><path d="M52.5 0V68"/><circle cx="52.5" cy="34" r="9.15"/></g><rect x="${box.x}" y="${box.y}" width="${box.width}" height="${box.height}" fill="#b7f37c15" stroke="#c7f796" stroke-width="1"/><path d="M${a.join(' ')} L${b.join(' ')}" stroke="${colors[passes[0].team]}" stroke-width="2.2"/></svg>`;
  }
  const ball=event.ball||[52.5,34];
  return `<svg class="polished-field" viewBox="${box.x} ${box.y} ${box.width} ${box.height}" role="img" aria-label="${esc(options.label||'Positions at the selected event')}"><defs><linearGradient id="${id}-grass" x2="1" y2="1"><stop stop-color="#22664d"/><stop offset="1" stop-color="#124a3b"/></linearGradient>${colors.map((c,i)=>`<marker id="${id}-${i}" markerWidth="3.5" markerHeight="3.5" refX="3" refY="1.75" orient="auto"><path d="M.2 .2L3.2 1.75L.2 3.3L1 1.75Z" fill="${c}"/></marker>`).join('')}</defs><rect x="-5" y="-6" width="115" height="80" fill="#0e302c"/><rect width="105" height="68" fill="url(#${id}-grass)"/>${Array.from({length:10},(_,i)=>`<rect x="${i*10.5}" width="10.5" height="68" fill="${i%2?'#ffffff05':'#00000007'}"/>`).join('')}<g fill="none" stroke="#e0eee58c" stroke-width=".18"><rect width="105" height="68"/><path d="M52.5 0V68"/><circle cx="52.5" cy="34" r="9.15"/><rect y="13.84" width="16.5" height="40.32"/><rect x="88.5" y="13.84" width="16.5" height="40.32"/><rect y="24.84" width="5.5" height="18.32"/><rect x="99.5" y="24.84" width="5.5" height="18.32"/></g><g fill="#082a28" stroke="#d8eee6aa" stroke-width=".18"><rect x="-3" y="30.34" width="3" height="7.32"/><rect x="105" y="30.34" width="3" height="7.32"/></g>${routes}${players}${options.hideBall?'':`<circle cx="${ball[0]}" cy="${ball[1]}" r=".45" fill="#fff" stroke="#18372c" stroke-width=".1"/>`}${overview}</svg>`;
 }
 root.EHField={draw,svgScene,passRoute,routeGeometry,createMotion,lastObservation:null};
})(window);
