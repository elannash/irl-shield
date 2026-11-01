export const title = 'Observed connection loss and delivered protective holds';
const output = (v) => {
  const p = v.policy;
  return p.connection || p.guard || p.chat || p.shield || v['local']
    ? 'HOLD' : v.coverage ? 'LIVE' : 'PROTECT';
};
export const state = (v) => {
  const out = output(v);
  const e = v.env;
  if (out === 'LIVE' && (!e.socketLive || !e.session || e.enabledGeneration !== e.generation
      || e.enabled.length !== 3 || v.policy.session !== e.session)) return 'LIVE without current control channel';
  if (out !== 'HOLD' && v.obligation.chat) return `Chat hold discarded: ${out}`;
  if (out !== 'HOLD' && v.obligation.shield) return `Shield begin discarded: ${out}`;
  return `${v.policy.phase}: ${out}`;
};
const labels = {
  QueueWelcome: 'welcome arrives; callback queues', EnableSubscription: 'current subscription enables',
  NewConnection: 'new socket opens', Welcome: 'queued welcome reaches policy',
  Fault: 'socket fault is observed', OldFault: 'socket fault is observed',
  BeginReconcile: 'Shield status read begins', Reconciled: 'Shield status returns',
  StartCompletion: 'current status starts completion', ApplyStatus: 'status callback applies',
  CheckStatus: 'status rechecked; newer Shield begin restored',
  ApplyConnectionRelease: 'connection callback clears its hold', CheckConnection: 'generation rechecked',
  ApplyGuardRelease: 'separate guard releases', FinishCompletion: 'completion returns',
  DeliverHold: 'authorized protective message arrives', ReleaseReceived: 'owner release arrives; raw Twitch order decides obligation',
  ClockAdvance: 'local receipt clock advances',
  Reconnect: 'approved handover begins', HandedOver: 'subscriptions migrate to new session',
  CoverageChange: 'coverage changes', LocalHold: 'local hold changes', StatusFailure: null, Idle: null,
};
export const step = (action) => Object.hasOwn(labels, action) ? labels[action] : action;
