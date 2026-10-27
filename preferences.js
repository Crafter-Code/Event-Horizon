                                                                             
(function(root){
  const keys=['possession','passes','shots','pressure','attacks','tempo','progress','tackles','movement'];
  const defaults=()=>({team:'all',player:'none',audience:'fan',language:'en',metrics:keys.slice(),overlay:false});
  function normalize(value){const result=defaults();if(!value||typeof value!=='object'||Array.isArray(value))return result;
    for(const [key,allowed] of Object.entries({team:['all','0','1'],audience:['fan','analyst','player'],language:['en','cs','de','fr','it','es','pt']}))if(allowed.includes(value[key]))result[key]=value[key];
    if(value.player==='none'||typeof value.player==='string'&&/^[01]:(?:[1-9]|10|11)$/.test(value.player))result.player=value.player;
    if(Array.isArray(value.metrics))result.metrics=keys.filter(key=>value.metrics.includes(key));
    if(typeof value.overlay==='boolean')result.overlay=value.overlay;return result;}
  const api={keys,defaults,normalize,load(storage){try{return normalize(JSON.parse(storage.getItem('event-horizon-fan')||'{}'));}catch{return defaults();}},
    save(storage,value){try{storage.setItem('event-horizon-fan',JSON.stringify(normalize(value)));return true;}catch{return false;}}};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.EHPreferences=api;
})(typeof window!=='undefined'?window:this);
