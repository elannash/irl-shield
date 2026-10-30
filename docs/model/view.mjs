export const title = 'Shield reconciliation, independent holds, and planned handover';
export const state = (v) => {
  if (v.releaseClobbered) return 'Reconciliation erased a required hold';
  if (v.replayed) return 'Repeated command executed';
  if (v.resumedBy === 'moderator') return 'Moderator resume executed';
  if (v.mode === 'LIVE' && !v.coverage) return 'LIVE without coverage';
  return `${v.phase}: ${v.mode}`;
};
export const step = (action) => ({
  Coverage: 'coverage changes', LocalHold: 'local hold changes',
  Welcome: 'server welcomes connection',
  Reconnect: 'approved planned handover begins', HandedOver: 'planned handover completes',
  Fault: 'connection faults or is revoked', BeginReconcile: 'status reconciliation begins',
  Reconciled: 'valid status returns', StatusFailure: 'status fails; retry under HOLD',
  RejectedCompletion: 'obsolete status is rejected', Deliver: 'notification arrives',
  Tick: 'time advances', Idle: null,
})[action] ?? action;
