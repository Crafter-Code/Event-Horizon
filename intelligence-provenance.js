                                                                               
(() => {
  const words = {
    en: {
      title:'Behind this match', source:'Synthetic football', data:'A 22-player simulation generates the events and images. No real Premier League match data is used.',
      seed:'Seed', model:'Model', scenario:'Scenario', open_play:'Open play', high_press:'High press', counterattack:'Fast counterattack',
      narrative:'Narrative in this run', local_factual:'Factual narrative', configured:'Foundry configured · awaiting result', verified:'Verified Foundry narrative applied', fallback:'Factual fallback',
      localNote:'Live explanations are calculated from the source events. No verified Foundry narrative has been applied in this run.',
      configuredNote:'The Foundry client is configured. The retained evidence does not currently confirm an applied, verified result.',
      verifiedNote:'A model-written explanation passed verification and was applied to a current episode.',
      fallbackNote:'A verified AI result is unavailable for the latest narrative. Source-based facts remain available.',
      checked:'Verified', pending:'Pending', fallbackCount:'Fallback', window:'Verified count covers the retained trace window (up to 24 jobs) in this run.',
      inspect:'Inspect agent evidence', generator:'Inspect the generator', proof:'Applied episode', latest:'Latest episode', status:'Status',
      unconfirmed:'Unconfirmed', pendingStatus:'Pending', verifiedStatus:'Verified', fallbackStatus:'Fallback'
    },
    cs: {
      title:'Co stojí za zápasem', source:'Syntetický fotbal', data:'Simulace 22 hráčů vytváří události i obraz. Nepoužívají se skutečná zápasová data Premier League.',
      seed:'Seed', model:'Model', scenario:'Scénář', open_play:'Otevřená hra', high_press:'Vysoký presink', counterattack:'Rychlý protiútok',
      narrative:'Příběh v tomto běhu', local_factual:'Faktický příběh', configured:'Foundry nastaveno · čekáme na výsledek', verified:'Ověřený příběh Foundry použit', fallback:'Faktická náhradní verze',
      localNote:'Živá vysvětlení vycházejí ze zdrojových událostí. V tomto běhu zatím nebyl použit ověřený příběh Foundry.',
      configuredNote:'Klient Foundry je nakonfigurován. Uchované důkazy nyní nepotvrzují použitý ověřený výsledek.',
      verifiedNote:'Vysvětlení vytvořené modelem prošlo kontrolou a bylo použito u aktuální epizody.',
      fallbackNote:'Pro poslední příběh není dostupný ověřený výsledek AI. Fakta ze zdrojů zůstávají dostupná.',
      checked:'Ověřeno', pending:'Čeká', fallbackCount:'Náhradní verze', window:'Počet ověřených výsledků pokrývá uchované záznamy tohoto běhu (nejvýše 24 úloh).',
      inspect:'Prohlédnout důkazy agentů', generator:'Prohlédnout generátor', proof:'Použitá epizoda', latest:'Poslední epizoda', status:'Stav',
      unconfirmed:'Nepotvrzeno', pendingStatus:'Čeká', verifiedStatus:'Ověřeno', fallbackStatus:'Náhradní verze'
    },
    de: {
      title:'Hinter diesem Spiel', source:'Synthetischer Fußball', data:'Eine Simulation mit 22 Spielern erzeugt Ereignisse und Bilder. Es werden keine realen Premier-League-Spieldaten verwendet.',
      seed:'Startwert', model:'Modell', scenario:'Szenario', open_play:'Offenes Spiel', high_press:'Hohes Pressing', counterattack:'Schneller Gegenangriff',
      narrative:'Erzählung in diesem Durchlauf', local_factual:'Faktenbasierte Erzählung', configured:'Foundry konfiguriert · Ergebnis ausstehend', verified:'Geprüfte Foundry-Erzählung angewendet', fallback:'Faktenbasierter Ersatz',
      localNote:'Live-Erklärungen werden aus Quellereignissen berechnet. In diesem Durchlauf wurde noch keine geprüfte Foundry-Erzählung angewendet.',
      configuredNote:'Der Foundry-Client ist konfiguriert. Die gespeicherten Nachweise bestätigen derzeit kein angewendetes, geprüftes Ergebnis.',
      verifiedNote:'Eine vom Modell verfasste Erklärung wurde geprüft und auf eine aktuelle Episode angewendet.',
      fallbackNote:'Für die letzte Erzählung ist kein geprüftes KI-Ergebnis verfügbar. Quellenbasierte Fakten bleiben verfügbar.',
      checked:'Geprüft', pending:'Ausstehend', fallbackCount:'Ersatz', window:'Die Zahl geprüfter Ergebnisse bezieht sich auf die gespeicherten Protokolle dieses Durchlaufs (bis zu 24 Aufträge).',
      inspect:'Agentennachweise prüfen', generator:'Generator prüfen', proof:'Angewendete Episode', latest:'Letzte Episode', status:'Status',
      unconfirmed:'Unbestätigt', pendingStatus:'Ausstehend', verifiedStatus:'Geprüft', fallbackStatus:'Ersatz'
    }
  };
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let signature = '';
  function update(provenance, language='en') {
    const root=document.getElementById('intelligence-provenance');
    if(!root||!provenance)return;
    const key=JSON.stringify([provenance,language]);
    if(key===signature)return;signature=key;
    const l=words[globalThis.EHLocale?.base(language)??language]||words.en,d=provenance.data,n=provenance.narrative;
    const status=['local_factual','configured','verified','fallback'].includes(n.status)?n.status:'local_factual';
    const note={local_factual:l.localNote,configured:l.configuredNote,verified:l.verifiedNote,fallback:l.fallbackNote}[status];
    const detailsOpen=root.querySelector('details')?.open||false;
    root.setAttribute('aria-label',l.title);
    root.innerHTML=`<div class="origin-data"><div class="origin-kicker">${esc(l.title)}</div><h2><span class="origin-symbol" aria-hidden="true">◉</span> ${esc(l.source)}</h2><p>${esc(l.data)}</p><div class="origin-settings"><span>${esc(l.seed)} <b>${esc(d.seed)}</b></span><span>${esc(l.scenario)} <b>${esc(l[d.scenario]||d.scenario)}</b></span></div><a href="/generator" target="_blank" rel="noopener">${esc(l.generator)} ↗</a></div><div class="origin-narrative" data-state="${status}"><div class="origin-kicker">${esc(l.narrative)}</div><h3><span class="origin-state-dot" aria-hidden="true"></span>${esc(l[status])}</h3><p>${esc(note)}</p><details ${detailsOpen?'open':''}><summary>${esc(l.inspect)}</summary><dl class="origin-counts"><div><dt>${esc(l.checked)}</dt><dd>${Number(n.counts.verified)||0}</dd></div><div><dt>${esc(l.pending)}</dt><dd>${Number(n.counts.pending)||0}</dd></div><div><dt>${esc(l.fallbackCount)}</dt><dd>${Number(n.counts.fallback)||0}</dd></div></dl><p class="origin-scope">${esc(l.window)}</p>${n.proof?`<p class="origin-scope">${esc(l.proof)}: ${esc(n.proof.episode_id)}<br><span class="origin-hash">${esc(n.proof.fact_fingerprint)}</span></p>`:''}<p class="origin-scope">${esc(l.model)}: ${esc(d.model_version)}</p><a href="/agent-trace" target="_blank" rel="noopener">${esc(l.inspect)} · JSON ↗</a></details></div>`;
  }
  window.EHIntelligenceProvenance={update};
})();
