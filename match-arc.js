                                                                                                     
(function (root) {
  'use strict';
  const labels = {
    en: {
      eyebrow: 'Beyond the scoreline', title: 'How the match unfolded', facts: 'Built from match facts',
      live: 'Story so far', complete: 'Completed period', waiting: 'The story starts with the first recorded events.',
      pending: 'Passes, chances and score changes will build the story as the match unfolds.',
      timeline: 'Checkpoints in match order', tip: 'Select a moment to inspect its source event.',
      score: 'Score', source: 'Open source event', events: 'events', allSources: 'Inspect the story’s sources',
      coverage: 'Events considered', bounds: 'Event range', fingerprint: 'Source fingerprint',
      evidence: 'Source events for the selected checkpoints', activity: 'Activity behind the story',
      passes: 'Completed passes', shots: 'Shots', tackles: 'Tackles', possession: 'Possession changes',
      pressure: 'Pressure changes', countNote: 'Activity values count events. Pressure changes are not pressure duration.',
      team0: 'Blue', team1: 'Red', shown: 'checkpoints shown', total: 'in this period',
      kinds: {goal:'Goal', opening_goal:'Opening goal', equalizer:'Equalizer', lead_restored:'Lead restored', takes_lead:'Takes the lead', extends_lead:'Lead extended', reduces_deficit:'Deficit reduced', first_shot:'First shot', kick_off:'Kick-off', kickoff:'Kick-off',
        half_time:'Half-time', full_time:'Full-time', pass_completed:'Completed pass',
        possession_change:'Possession change', pressure_change:'Pressure change', tackle:'Tackle'}
    },
    cs: {
      eyebrow: 'Více než skóre', title: 'Jak se zápas vyvíjel', facts: 'Z faktů ze zápasu',
      live: 'Dosavadní příběh', complete: 'Dokončený úsek', waiting: 'Příběh začíná prvními zaznamenanými událostmi.',
      pending: 'Přihrávky, šance a změny skóre postupně vytvoří příběh zápasu.',
      timeline: 'Klíčové okamžiky v pořadí zápasu', tip: 'Vyberte okamžik a prohlédněte si jeho zdrojovou událost.',
      score: 'Skóre', source: 'Otevřít zdrojovou událost', events: 'událostí', allSources: 'Prohlédnout zdroje příběhu',
      coverage: 'Zahrnuté události', bounds: 'Rozsah událostí', fingerprint: 'Otisk zdrojů',
      evidence: 'Zdrojové události vybraných okamžiků', activity: 'Události za příběhem',
      passes: 'Přesné přihrávky', shots: 'Střely', tackles: 'Odebrání míče', possession: 'Změny držení míče',
      pressure: 'Změny presinku', countNote: 'Hodnoty počítají události. Změny presinku nevyjadřují jeho dobu trvání.',
      team0: 'Modří', team1: 'Červení', shown: 'zobrazených okamžiků', total: 'v tomto úseku',
      kinds: {goal:'Gól', opening_goal:'Úvodní gól', equalizer:'Vyrovnání', lead_restored:'Obnovené vedení', takes_lead:'Převzetí vedení', extends_lead:'Zvýšené vedení', reduces_deficit:'Snížení rozdílu', first_shot:'První střela', kick_off:'Výkop', kickoff:'Výkop',
        half_time:'Poločas', full_time:'Konec zápasu', pass_completed:'Přesná přihrávka',
        possession_change:'Změna držení míče', pressure_change:'Změna presinku', tackle:'Odebrání míče'}
    },
    de: {
      eyebrow: 'Mehr als der Spielstand', title: 'So entwickelte sich das Spiel', facts: 'Aus den Spielfakten erstellt',
      live: 'Bisheriger Spielverlauf', complete: 'Abgeschlossener Zeitraum', waiting: 'Die Geschichte beginnt mit den ersten erfassten Ereignissen.',
      pending: 'Pässe, Chancen und Spielstandänderungen ergeben nach und nach die Spielgeschichte.',
      timeline: 'Momente in Spielreihenfolge', tip: 'Wählen Sie einen Moment, um sein Quellereignis zu prüfen.',
      score: 'Spielstand', source: 'Quellereignis öffnen', events: 'Ereignisse', allSources: 'Quellen der Geschichte prüfen',
      coverage: 'Berücksichtigte Ereignisse', bounds: 'Ereignisbereich', fingerprint: 'Quellfingerabdruck',
      evidence: 'Quellereignisse der ausgewählten Momente', activity: 'Ereignisse hinter der Geschichte',
      passes: 'Erfolgreiche Pässe', shots: 'Schüsse', tackles: 'Balleroberungen', possession: 'Ballbesitzwechsel',
      pressure: 'Druckwechsel', countNote: 'Die Werte zählen Ereignisse. Druckwechsel sind keine Druckdauer.',
      team0: 'Blau', team1: 'Rot', shown: 'Momente angezeigt', total: 'in diesem Zeitraum',
      kinds: {goal:'Tor', opening_goal:'Eröffnungstor', equalizer:'Ausgleich', lead_restored:'Führung zurückgewonnen', takes_lead:'Führung übernommen', extends_lead:'Führung ausgebaut', reduces_deficit:'Rückstand verkürzt', first_shot:'Erster Schuss', kick_off:'Anstoß', kickoff:'Anstoß',
        half_time:'Halbzeit', full_time:'Spielende', pass_completed:'Erfolgreicher Pass',
        possession_change:'Ballbesitzwechsel', pressure_change:'Druckwechsel', tackle:'Balleroberung'}
    }
  };
  const escape = value => String(value == null ? '' : value).replace(/[&<>"']/g,
    char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const integer = value => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
  const eventId = value => integer(value) !== null && value > 0 ? value : null;
  const clock = value => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '—';
    return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
  };
  const pair = value => Array.isArray(value) && value.length === 2 && value.every(v => integer(v) !== null) ? value : null;
  const ids = value => [...new Set((Array.isArray(value) ? value : []).map(eventId).filter(v => v !== null))];

  function markup(arc, language) {
    const lang = Object.prototype.hasOwnProperty.call(labels, language) ? language : 'en';
    const copy = labels[globalThis.EHLocale?.base(lang)??lang];
    const number = value => integer(value) === null ? '—' : value.toLocaleString(lang);
    const sourceButton = id => `<button type="button" data-arc-event="${id}" aria-label="${escape(copy.source)} #${id}">#${id}</button>`;
    if (!arc || typeof arc !== 'object') {
      return `<section class="match-arc match-arc--pending" aria-label="${escape(copy.eyebrow)}"><div class="match-arc__eyebrow">${escape(copy.eyebrow)}</div><h3 class="match-arc__title">${escape(copy.waiting)}</h3><p class="match-arc__lead">${escape(copy.pending)}</p></section>`;
    }
    const checkpoints = (Array.isArray(arc.checkpoints) ? arc.checkpoints : []).filter(p => p && typeof p === 'object').slice(0, 12);
    const coverage = arc.coverage && typeof arc.coverage === 'object' ? arc.coverage : {};
    const counts = arc.counts && typeof arc.counts === 'object' ? arc.counts : {};
    const sourceIds = ids(arc.source_event_ids);
    const displayTitle = arc.title || copy.title;
    const narrative = arc.narrative || (checkpoints.length ? '' : copy.waiting);
    const activity = [
      ['passes', counts.completed_passes, true], ['shots', counts.shots, true],
      ['tackles', counts.tackles, true], ['possession', counts.possession_changes, false],
      ['pressure', counts.pressure_changes, false]
    ].map(([key, value, split]) => {
      const teams = split ? pair(value) : null;
      const total = split ? (teams ? teams[0] + teams[1] : null) : value;
      return `<div class="match-arc__activity-item"><dt>${escape(copy[key])}</dt><dd>${number(total)}${teams ? `<div class="match-arc__teams"><span>${escape(copy.team0)} ${number(teams[0])}</span><span>${escape(copy.team1)} ${number(teams[1])}</span></div>` : `<div class="match-arc__unit">${escape(copy.events)}</div>`}</dd></div>`;
    }).join('');
    const checkpointMarkup = checkpoints.map((point, index) => {
      const id = eventId(point.event_id);
      const score = pair(point.score);
      const knownKind = Object.prototype.hasOwnProperty.call(copy.kinds, point.kind) ? copy.kinds[point.kind] : '';
      const goalKinds = ['goal', 'opening_goal', 'equalizer', 'lead_restored', 'takes_lead', 'extends_lead', 'reduces_deficit'];
      const kindClass = goalKinds.includes(point.kind) ? ' match-arc__checkpoint--goal' : '';
      const tag = id === null ? 'div' : 'button';
      const action = id === null ? '' : ` type="button" data-arc-event="${id}"`;
      return `<li class="match-arc__checkpoint${kindClass}"><span class="match-arc__marker" aria-hidden="true">${String(index + 1).padStart(2, '0')}</span><${tag} class="match-arc__moment"${action}><span class="match-arc__moment-top"><time>${clock(point.time)}</time>${score ? `<span class="match-arc__score"><span>${escape(copy.score)}</span><b>${score[0]} : ${score[1]}</b></span>` : ''}</span>${knownKind ? `<span class="match-arc__kind">${escape(knownKind)}</span>` : ''}<strong class="match-arc__moment-title">${escape(point.title || knownKind)}</strong>${point.text ? `<span class="match-arc__moment-text">${escape(point.text)}</span>` : ''}${id === null ? '' : `<span class="match-arc__source-link">${escape(copy.source)} #${id}<span aria-hidden="true"> ↗</span></span>`}</${tag}></li>`;
    }).join('');
    const checkpointCount = integer(arc.checkpoint_count);
    const truncated = Boolean(arc.checkpoints_truncated) || (checkpointCount !== null && checkpointCount > checkpoints.length);
    const truncation = truncated ? `<p class="match-arc__truncation">${checkpoints.length} ${escape(copy.shown)} · ${number(checkpointCount)} ${escape(copy.total)}.</p>` : '';
    const first = eventId(coverage.first_event_id), last = eventId(coverage.last_event_id);
    return `<section class="match-arc" aria-label="${escape(copy.eyebrow)}">
      <div class="match-arc__heading"><div><div class="match-arc__eyebrow">${escape(copy.eyebrow)}</div><h3 class="match-arc__title">${escape(displayTitle)}</h3></div><span class="match-arc__fact-badge">${escape(copy.facts)}</span></div>
      <div class="match-arc__window"><span class="match-arc__state${arc.complete ? ' match-arc__state--complete' : ''}">${escape(arc.complete ? copy.complete : copy.live)}</span><span>${clock(arc.start)}–${clock(arc.end)}</span></div>
      ${narrative ? `<p class="match-arc__lead">${escape(narrative)}</p>` : ''}
      ${checkpoints.length ? `<div class="match-arc__rail-heading"><h4>${escape(copy.timeline)}</h4><p>${escape(copy.tip)}</p></div><ol class="match-arc__rail" tabindex="0" aria-label="${escape(copy.timeline)}">${checkpointMarkup}</ol>${truncation}` : `<p class="match-arc__pending-note">${escape(copy.pending)}</p>`}
      <div class="match-arc__activity-heading">${escape(copy.activity)}</div><dl class="match-arc__activity">${activity}</dl><p class="match-arc__count-note">${escape(copy.countNote)}</p>
      <details class="match-arc__sources"><summary>${escape(copy.allSources)}</summary><div class="match-arc__coverage"><span>${escape(copy.coverage)} <strong>${number(coverage.event_count)}</strong></span>${first !== null && last !== null ? `<span>${escape(copy.bounds)} <strong>#${first}–#${last}</strong></span>` : ''}</div>${sourceIds.length ? `<p class="match-arc__evidence-label">${escape(copy.evidence)}</p><div class="match-arc__source-buttons">${sourceIds.map(sourceButton).join('')}</div>` : ''}${coverage.source_sha256 ? `<p class="match-arc__hash">${escape(copy.fingerprint)} · SHA-256<br><code>${escape(coverage.source_sha256)}</code></p>` : ''}</details>
    </section>`;
  }
  const api = {markup};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else {
    root.EHMatchArc = api;
                                                                            
    root.document.addEventListener('focusin', event => {
      const card = event.target.closest?.('.match-arc__moment');
      if (card) card.scrollIntoView({block:'nearest', inline:'nearest'});
    });
  }
})(typeof window !== 'undefined' ? window : this);
