                                                                           
(() => {
  const $ = id => document.getElementById(id);
  const episode = $('episode'), language = $('language'), team = $('team'), player = $('player');
  const saved = window.EHPreferences.load(localStorage);
  language.value = saved.language;
  team.value = saved.team;
  for (let side = 0; side < 2; side++) for (let number = 1; number <= 11; number++) {
    const option = document.createElement('option');
    option.value = `${side}:${number}`; option.textContent = `${side ? 'Red' : 'Blue'} · #${number}`;
    player.append(option);
  }
  player.value = saved.player;
  let runKey = null, busy = false;
  const put = (id, value) => { $(id).textContent = value ?? ''; };
  const line = (label, value, className='') => {
    const row = document.createElement('div'); row.className = className;
    const title = document.createElement('small'); title.textContent = label;
    const body = document.createElement('p'); body.textContent = value;
    row.append(title, body); return row;
  };
  const clear = id => { const node = $(id); node.replaceChildren(); return node; };
  const stringify = value => Array.isArray(value) ? value.join(' : ') : String(value);
  function render(data) {
    if (runKey && runKey !== data.run_key) episode.value = '';
    runKey = data.run_key;
    const previous = episode.value;
    episode.replaceChildren();
    const latest = new Option('Follow latest', ''); episode.add(latest);
    for (const item of data.episodes.slice().reverse()) {
      const option = new Option(`${Math.floor(item.time / 60)}′ · ${item.title}`, item.id);
      episode.add(option);
    }
    episode.value = [...episode.options].some(option => option.value === previous) ? previous : '';
    put('status', `LIVE · ${Math.floor(data.clock / 60)}:${String(Math.floor(data.clock % 60)).padStart(2,'0')} · ${data.event_count} confirmed events · ${data.episodes.length} recent episodes`);
    const selected = data.selected;
    for (const node of document.querySelectorAll('[data-stage]')) {
      node.classList.toggle('ready', Boolean(selected?.stages[node.dataset.stage]));
      node.classList.toggle('onair', node.dataset.stage === 'on_air' && Boolean(selected?.stages.on_air));
    }
    if (!selected) {
      put('title', 'Waiting for a key moment');
      put('meta', 'The match is live. The first source-linked episode will appear automatically.');
      for (const id of ['story', 'sources', 'studio', 'broadcast', 'stream', 'metrics', 'integrity']) clear(id);
      return;
    }
    put('title', selected.story.title);
    put('meta', `${selected.clock} · episode ${selected.id} · revision ${selected.revision} · ${selected.complete ? 'outcome confirmed' : 'outcome pending'}`);
    const story = clear('story');
    for (const [label, key] of [['What happened', 'what'], ['Why it matters', 'why'], ['How the game is changing', 'change']])
      story.append(line(label, selected.story[key], 'story-row'));
    if (selected.agent.interpretation) story.append(line('Verified agent interpretation · English',
      `${selected.agent.interpretation.what} ${selected.agent.interpretation.why} ${selected.agent.interpretation.change}`, 'story-row'));
    const metrics = clear('metrics');
    for (const metric of selected.metrics) {
      const row = document.createElement('div'); row.className = 'metric';
      const label = document.createElement('span'); label.textContent = metric.label;
      const value = document.createElement('strong'); value.textContent = stringify(metric.value) + (metric.unit === 'seconds' ? ' s' : '');
      row.append(label, value); metrics.append(row);
    }
    put('integrity', `${selected.verified ? 'All' : 'Some'} source checks passed (${selected.checks.filter(check => check.passed).length}/${selected.checks.length}). Shared fact fingerprint: ${selected.fact_fingerprint.slice(0,16)}…`);
    const sources = clear('sources');
    for (const source of selected.sources) {
      const row = document.createElement('div'); row.className = 'source';
      const link = document.createElement('a'); link.href = `/event?id=${encodeURIComponent(source.id)}&run_key=${encodeURIComponent(data.run_key)}&language=${encodeURIComponent(data.language)}`;
      link.textContent = `#${source.id}`;
      const time = document.createElement('span'); time.textContent = `${Math.floor(source.time / 60)}:${String(Math.floor(source.time % 60)).padStart(2,'0')}`;
      const description = document.createElement('div'); description.textContent = `${source.title} · ${source.text}`;
      row.append(link, time, description); sources.append(row);
    }
    if (selected.source_count > selected.sources_shown) {
      const note = document.createElement('p'); note.className = 'muted';
      note.textContent = `Showing ${selected.sources_shown} of ${selected.source_count} source events. Every source ID contributes to the episode fingerprint.`;
      sources.append(note);
    }
    const studio = clear('studio');
    studio.append(line('Lead', selected.studio.lead, 'format'));
    for (const point of selected.studio.talking_points) studio.append(line('Talking point', point, 'format'));
    studio.append(line('Editorial boundary', selected.studio.boundary, 'format'));
    studio.append(line('Narrative engine', selected.agent.status === 'verified' ? 'Foundry agent analysis verified against the episode sources.' : 'Deterministic factual explanation; agent status: ' + selected.agent.status.replaceAll('_',' ') + '.', 'format'));
    const broadcast = clear('broadcast');
    const aired = selected.broadcast.status === 'on_air';
    broadcast.append(line(aired ? 'Selected for the preview' : 'Producer decision', aired ? selected.broadcast.text : `${selected.broadcast.status.replaceAll('_',' ')} · awaiting current approved caption`, 'format'));
    if (aired) broadcast.append(line('Review receipt', selected.broadcast.receipt, 'format'));
    const stream = clear('stream');
    stream.append(line(selected.stream.focus, selected.stream.personal, 'format'));
    stream.append(line('Why you see this', selected.stream.reason, 'format'));
  }
  async function refresh() {
    if (busy) return; busy = true;
    try {
      const query = new URLSearchParams({team:team.value,player:player.value,language:language.value});
      if (episode.value) query.set('episode', episode.value);
      const response = await fetch(`/journey/state?${query}`, {cache:'no-store'});
      if (!response.ok) throw Error(`Live data unavailable (${response.status})`);
      render(await response.json());
    } catch (error) { put('status', error.message); $('status').classList.add('error'); }
    finally { busy = false; }
  }
  for (const node of [episode,language,team,player]) node.addEventListener('change', () => {
    if (node !== episode) {
      const previous = window.EHPreferences.load(localStorage);
      window.EHPreferences.save(localStorage,{...previous,language:language.value,team:team.value,player:player.value});
    }
    refresh();
  });
  refresh(); setInterval(refresh, 1200);
})();
