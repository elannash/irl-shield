'use strict';
(() => {
  let token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
  history.replaceState(null, '', location.pathname);
  let timer;
  let qrBlob;
  let refreshGeneration = 0;
  let refreshing = false;
  let pairGeneration = 0;
  let controlsObserver;
  const root = document.getElementById('root');
  const byId = id => document.getElementById(id);
  const reasons = {
    startup: 'Waiting for protected video.', manual: 'Your manual hold is active.',
    chat: 'Chat requested a hold.', shield_mode: 'Twitch Shield Mode is active.',
    transport: 'Waiting for the stream connection.', egress: 'Waiting for protected output.',
    coverage: 'Checking privacy coverage.', clear: 'Privacy coverage is current.',
    ok: 'Privacy coverage is current.', stale: 'Waiting for fresh privacy coverage.',
    unknown: 'Protection state supplied by the stream controller.'
  };
  function controlState(state, reason) {
    byId('control-state').textContent = state;
    const manual = state === 'HOLD' && reason === 'manual';
    byId('hold').classList.toggle('primary', !manual);
    byId('resume').classList.toggle('primary', manual);
  }
  async function request(path, options = {}) {
    const response = await fetch(path, {
      signal: AbortSignal.timeout(4000), ...options, cache: 'no-store', credentials: 'omit', redirect: 'error',
      referrerPolicy: 'no-referrer',
      headers: {Authorization: `Bearer ${token}`, ...options.headers}
    });
    if (!response.ok) throw new Error('Private request failed');
    return response;
  }
  function clearPairing() {
    pairGeneration += 1;
    if (qrBlob) URL.revokeObjectURL(qrBlob);
    qrBlob = null;
    if (!byId('qr')) return;
    byId('qr').removeAttribute('src');
    byId('qr').hidden = true;
    byId('import').removeAttribute('href');
    byId('import').hidden = true;
    byId('stream-url').value = '';
  }
  function stale() {
    byId('state').textContent = 'Unavailable';
    byId('state').dataset.state = 'UNKNOWN';
    controlState('Unavailable', 'unknown');
    byId('reason').textContent = 'Status connection lost. Check the relay terminal.';
    byId('connection').textContent = 'The current video state is unknown.';
    byId('clues').textContent = '—';
    byId('faces').textContent = '—';
    byId('totals-unavailable').hidden = true;
    byId('risk').hidden = true;
    byId('skin').textContent = '—';
    byId('locked').textContent = '—';
    byId('votes').textContent = 'Votes unavailable.';
  }
  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    const generation = ++refreshGeneration;
    try {
      const data = await (await request('/private/snapshot')).json();
      if (generation !== refreshGeneration || document.hidden) return;
      byId('state').textContent = data.state;
      byId('state').dataset.state = data.state;
      controlState(data.state, data.reason_code);
      byId('reason').textContent = reasons[data.reason_code] || reasons.unknown;
      byId('connection').textContent = 'Connected · private streamer view';
      byId('clues').textContent = data.clues_hidden === null ? '—' : data.clues_hidden.toLocaleString();
      byId('faces').textContent = data.faces_hidden === null ? '—' : data.faces_hidden.toLocaleString();
      byId('totals-unavailable').hidden = data.clues_hidden !== null && data.faces_hidden !== null;
      byId('face-mode').textContent = data.face_mode;
      byId('skin').textContent = data.skin;
      byId('locked').textContent = data.skin_locked ? 'Locked by moderator' : 'Chat voting';
      const votes = Object.entries(data.votes).map(([skin, count]) => `${skin}: ${count}`);
      byId('votes').textContent = votes.length ? votes.join(' · ') : 'No current votes.';
      byId('risk').hidden = data.geo_risk === undefined;
      if (data.geo_risk !== undefined) {
        byId('risk').textContent = `Location risk estimate: ${Math.round(data.geo_risk * 100)}% · ${Math.floor(data.geo_risk_age_s)}s old`;
      }
    } catch { if (generation === refreshGeneration) stale(); }
    finally { refreshing = false; }
  }
  async function setHold(active) {
    byId('hold').disabled = byId('resume').disabled = true;
    byId('action').textContent = active ? 'Requesting hold…' : 'Clearing manual hold…';
    try {
      await request('/private/hold', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({active})});
      byId('action').textContent = active ? 'Manual hold requested.' : 'Manual hold cleared. Other protection may remain.';
      await refresh();
    } catch {
      byId('action').textContent = 'Request not confirmed. Check the relay before continuing.';
    } finally {
      byId('hold').disabled = byId('resume').disabled = false;
    }
  }
  async function showPairing() {
    clearPairing();
    const generation = pairGeneration;
    const protocol = byId('protocol').value;
    byId('pair-message').textContent = 'Loading private pairing…';
    try {
      const data = await (await request('/private/pairing')).json();
      const image = await (await request(`/private/qr/${protocol}.png`)).blob();
      if (generation !== pairGeneration || !byId('pairing').open || document.hidden) return;
      const srtOption = byId('protocol').querySelector('[value="srt"]');
      if (data.srt_url && !srtOption) byId('protocol').add(new Option('SRT', 'srt'));
      byId('qualification').textContent = protocol === 'srt'
        ? (data.srt_status === 'qualified' ? 'Native SRT qualified by the relay operator.' : 'SRT is unqualified. Phone-to-relay streaming has not been verified.')
        : 'RTMP configuration import · device import has not been verified.';
      byId('stream-url').value = data[`${protocol}_url`];
      byId('import').href = data[`${protocol}_import`];
      byId('import').hidden = false;
      qrBlob = URL.createObjectURL(image);
      byId('qr').src = qrBlob;
      byId('qr').hidden = false;
      byId('pair-message').textContent = 'Scan on another device, or open in Moblin on this phone.';
    } catch {
      if (generation !== pairGeneration) return;
      clearPairing();
      byId('pair-message').textContent = 'Pairing unavailable. Check the relay terminal.';
    }
  }
  async function connect() {
    try {
      const response = await request('/private/ui');
      root.innerHTML = await response.text();
      controlsObserver?.disconnect();
      controlsObserver = new ResizeObserver(() => {
        document.documentElement.style.setProperty('--control-height',
          `${Math.ceil(byId('controls').getBoundingClientRect().height)}px`);
      });
      controlsObserver.observe(byId('controls'));
      byId('hold').addEventListener('click', () => setHold(true));
      byId('resume').addEventListener('click', () => setHold(false));
      byId('pairing').addEventListener('toggle', () => {
        if (byId('pairing').open) showPairing(); else clearPairing();
      });
      byId('protocol').addEventListener('change', showPairing);
      byId('copy').addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(byId('stream-url').value);
          byId('pair-message').textContent = 'Stream URL copied. Keep it private.';
        } catch {
          byId('stream-url').focus();
          byId('stream-url').select();
          byId('pair-message').textContent = 'Select and copy the URL above. Clipboard access is unavailable here.';
        }
      });
      await refresh();
      timer = setInterval(() => { if (!document.hidden) refresh(); }, 1000);
    } catch {
      token = '';
      byId('login-error').textContent = 'Cannot connect. Use the current private link from the relay terminal.';
    }
  }
  byId('authorize').addEventListener('submit', event => {
    event.preventDefault();
    token = byId('token').value;
    byId('token').value = '';
    connect();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearPairing();
      if (byId('pairing')) byId('pairing').open = false;
      if (byId('state')) stale();
    } else if (byId('state')) refresh();
  });
  window.addEventListener('pagehide', () => {
    controlsObserver?.disconnect();
    clearInterval(timer);
    clearPairing();
    token = '';
    if (byId('state')) stale();
  });
  if (token) connect();
})();
