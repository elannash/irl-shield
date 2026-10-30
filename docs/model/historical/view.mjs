export const title = 'Twitch protection and replay checks';
// Keep broken states separate from ordinary protected states in trace charts.
export const state = (v) => {
  if (v.replayed) return 'Repeated command executed';
  if (v.resumedBy === 'moderator') return 'Moderator resume executed';
  if (v.mode === 'LIVE' && !v.coverage) return 'LIVE without coverage';
  return `${v.phase}: ${v.mode}`;
};
export const step = (action) => ({
  Coverage: 'coverage changes', LocalHold: 'local hold changes',
  Welcome: 'server welcomes connection', Ready: 'subscriptions ready',
  Reconnect: 'server requests reconnect', Fault: 'connection faults or is revoked',
  Deliver: 'notification arrives', Tick: 'time advances', Idle: null,
})[action] ?? action;
