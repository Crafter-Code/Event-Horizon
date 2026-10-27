(() => {
  const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const copy={

    de:{"kicker":"Szenario → Video → Prüfung","heading":"Generator-Steckbrief","select":"Szenario","checked":"Konsistenz geprüft","failed":"Abweichung erkannt","frames":"Geprüfte Bilder","events":"Ereignisse","passed":"Bestätigt","pending":"Ausstehend","missed":"Nicht erfüllt","deadline":"bis","seconds":"s","source":"Ereignis","free":"Freies Spiel hat keine vorgegebene Folge. Das Modell bestimmt Ereignisse und Ergebnisse.","download":"Referenzclip herunterladen · 15 s","json":"Prüfungen · JSON","note":"Der Clip wird mit dem aktuellen Startwert und Szenario neu erzeugt: 20 Bilder/s, Anmerkungen, Vorhersagen und Prüfsummen. Die Anmerkungen bewerten die Erkennung nach der Bildanalyse.","scope":"Diese Prüfungen bewerten den Generator. Die Erkennungsqualität wird separat in der Videoanalyse gezeigt.","replay":"Gleicher Startwert und gleiches Szenario erzeugen dasselbe Spiel. Ereignisse treffen im Spielverlauf ein."},
    en:{kicker:'Scenario → video → verification',heading:'Generator passport',select:'Scenario',checked:'Consistency verified',failed:'Inconsistency detected',frames:'Frames checked',events:'Events',passed:'Confirmed',pending:'Pending',missed:'Not met',deadline:'by',seconds:'s',source:'Event',free:'Open play has no scripted chain. The model determines events and outcomes.',download:'Download reference clip · 15 s',json:'Checks · JSON',note:'The clip is regenerated with the current seed and scenario: 20 fps, annotations, predictions and checksums. Labels evaluate recognition after image analysis.',scope:'These checks validate the generator. Recognition quality is shown separately in video analysis.',replay:'The same seed and scenario reproduce the match. Events arrive as play unfolds.'},
    cs:{kicker:'Scénář → video → ověření',heading:'Pas generátoru',select:'Scénář',checked:'Konzistence ověřena',failed:'Zjištěn nesoulad',frames:'Ověřené snímky',events:'Události',passed:'Potvrzeno',pending:'Čeká se',missed:'Nesplněno',deadline:'do',seconds:'s',source:'Událost',free:'Volná hra nemá předepsanou posloupnost. Události a výsledky určuje model.',download:'Stáhnout referenční klip · 15 s',json:'Kontroly · JSON',note:'Klip se vytvoří znovu s aktuálním seed a scénářem: 20 snímků/s, anotace, předpovědi a kontrolní součty. Anotace ověřují rozpoznávání až po analýze obrazu.',scope:'Tyto kontroly ověřují generátor. Kvalita rozpoznávání je zvlášť v analýze videa.',replay:'Stejný seed a scénář zopakují zápas. Události přicházejí v průběhu hry.'}
  };
  const recognitionCopy={
    de:{label:'Bilderkennung',matched:'Erkannt',missed:'Übersehen',pending:'Prüfung läuft',no_source_event:'Kein Quellereignis',pending_source:'Warten auf Ereignis',frame:'Bild',expired:'nicht mehr im Live-Puffer'},
    en:{label:'Pixel model',matched:'Recognized',missed:'Missed',pending:'Evaluation pending',no_source_event:'No source event',pending_source:'Awaiting source event',frame:'Frame',expired:'expired from live buffer'},
    cs:{label:'Rozpoznání z obrazu',matched:'Rozpoznáno',missed:'Vynecháno',pending:'Kontrola čeká',no_source_event:'Bez zdrojové události',pending_source:'Čeká na událost',frame:'Snímek',expired:'již není v živé paměti'}
  };
  $('scenario-lab').dataset.localized='true';
  let catalog=[],state=null,version='';
  fetch('/scenarios',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{catalog=data.scenarios;if(state)update(state);}).catch(()=>{});
  function update(s){
    state=s;const g=s.generator;if(!g)return;
    const language=window.EHSettings().language,l=copy[globalThis.EHLocale?.base(language)??language],scenario=g.scenario;
    $('scenario-select-label').textContent=l.select;$('scenario-replay-note').textContent=l.replay;
    for(const p of catalog){let option=$('scenario-select').querySelector(`option[value="${p.id}"]`);if(!option){option=document.createElement('option');option.value=p.id;$('scenario-select').append(option);}option.textContent=p.title[globalThis.EHLocale?.base(language)??language];}
                                                                                          
    const key=[s.run_key,language,g.status,Math.floor(s.clock),JSON.stringify(scenario.expectations)].join(':');
    if(version===key)return;version=key;
    const words=recognitionCopy[globalThis.EHLocale?.base(language)??language],range=s.vision?.frame_range;
    const steps=scenario.expectations.map(t=>{
      const recognition=t.recognition,frames=recognition?.frame_ids||[];
      const proof=recognition?`<span class="scenario-recognition ${esc(recognition.status)}">${words.label}: ${words[recognition.status]||esc(recognition.status)}${recognition.prediction_id?' · '+esc(recognition.prediction_id):''}</span>${frames.map(id=>range&&id>=range[0]&&id<=range[1]?`<a href="/video/frame.png?${new URLSearchParams({id,run_key:s.run_key})}" target="_blank" rel="noopener">${words.frame} #${id}</a>`:`<span class="scenario-frame-expired">${words.frame} #${id} · ${words.expired}</span>`).join(' ')}`:'';
      return `<li class="${esc(t.status)}"><strong>${esc(t.label[globalThis.EHLocale?.base(language)??language])}</strong><small>${esc(t.status==='passed'?l.passed:t.status==='failed'?l.missed:l.pending)} · ${esc(l.deadline)} ${t.by_s} ${l.seconds}</small>${t.evidence?`<a href="/event?${new URLSearchParams({run_key:s.run_key,id:t.evidence.event_id,language})}" target="_blank" rel="noopener">${l.source} #${t.evidence.event_id} · ${t.evidence.time.toFixed(2)} ${l.seconds}</a>`:''}${proof}</li>`;
    }).join('');
    const query=new URLSearchParams({scenario:scenario.id,seed:s.settings.seed,seconds:15});
    $('scenario-lab').innerHTML=`<div class="scenario-top"><div><span class="section-label">${l.kicker}</span><h2>${esc(scenario.title[globalThis.EHLocale?.base(language)??language])} <small class="muted">· v${scenario.version}</small></h2></div><span class="scenario-verified ${g.status==='failed'?'failed':''}">${g.status==='failed'?l.failed:l.checked}</span></div><p class="scenario-description">${esc(scenario.description[globalThis.EHLocale?.base(language)??language])}</p><div class="muted" style="font-size:12px">${l.frames}: ${g.checked_frames.toLocaleString(language)} · ${l.events}: ${g.checked_events.toLocaleString(language)} · seed ${s.settings.seed}</div>${steps?`<ol class="scenario-steps">${steps}</ol>`:`<p class="scenario-footnote">${l.free}</p>`}<p class="scenario-footnote">${l.scope}</p><div class="scenario-actions"><a id="download-dataset" href="/dataset.zip?${query}" download>${l.download}</a><a href="/generator" target="_blank" rel="noopener">${l.json}</a></div><p class="scenario-footnote">${l.note}</p>`;
    $('scenario-lab').setAttribute('aria-label',l.heading);
  }
  window.EHScenario={update};
})();
