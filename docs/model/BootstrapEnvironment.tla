------------------------- MODULE BootstrapEnvironment -------------------------
EXTENDS Integers, Sequences, FiniteSets, TLC
CONSTANTS MaxGeneration, MaxQueries, HoldStamps, ReleaseStamps, LocalNow,
          StartedAt, Missing, ForwardSkew, ClockTick, MaxAge, InitialBarrier,
          ObservationStamps, MaxHolds
VARIABLES env, policy, queries, obligation, received, execution, coverage, local
vars == <<env, policy, queries, obligation, received, execution, coverage, local>>
Topics == {"chat", "begin", "end"}
Sources == {"chat", "shield"}
Min(a,b) == IF a < b THEN a ELSE b
Max(a,b) == IF a > b THEN a ELSE b

\* This truth belongs to the environment, not to policy's connection flag.
EnvironmentInit ==
  /\ env = [generation |-> 1, socketLive |-> TRUE, session |-> 0,
             enabledGeneration |-> 0, enabled |-> {}, queuedWelcome |-> {},
             callbackOrigin |-> 0, registry |-> {}, everSubscribed |-> FALSE,
             shieldTruth |-> FALSE, now |-> LocalNow, rawHighWater |-> InitialBarrier,
             observations |-> {}, helixObserved |-> FALSE, truthRaised |-> FALSE,
             helix |-> [stamp |-> Missing, receipt |-> 0,
                         priorHighWater |-> InitialBarrier, bootstrapStamp |-> InitialBarrier],
             holds |-> [s \in Sources |-> [stamp |-> Missing, receipt |-> 0,
                         priorHighWater |-> InitialBarrier, bootstrapStamp |-> InitialBarrier]]]
  /\ queries = <<>> /\ obligation = [chat |-> FALSE, shield |-> FALSE]
  /\ received = {} /\ execution = [pc |-> "idle", token |-> 0]
  /\ coverage = TRUE /\ local = FALSE

\* Init is after opening the first socket (connection_started in fixed code),
\* before its welcome. Session IDs are represented by their connection origin.
InitialPolicy(g) == [generation |-> g, live |-> FALSE, session |-> 0,
  phase |-> "connecting", revoked |-> FALSE, connection |-> TRUE,
  guard |-> FALSE, chat |-> FALSE, shield |-> FALSE,
  revision |-> 0, chatTime |-> StartedAt - 1, shieldTime |-> StartedAt - 1,
  rawHighWater |-> InitialBarrier, pending |-> [s \in Sources |-> FALSE], token |-> 0]

Output == IF policy.connection \/ policy.guard \/ policy.chat \/ policy.shield \/ local
          THEN "HOLD" ELSE IF coverage THEN "LIVE" ELSE "PROTECT"
ActualCurrentChannel == env.socketLive /\ env.session # 0
  /\ env.enabledGeneration = env.generation /\ env.enabled = Topics
  /\ policy.session = env.session

QueueWelcome ==
  /\ env.socketLive /\ env.session = 0
  /\ env' = [env EXCEPT !.session = env.generation,
                          !.queuedWelcome = @ \cup {env.generation}]
  /\ UNCHANGED <<policy, queries, obligation, received, execution, coverage, local>>
EnableSubscription(t) ==
  /\ env.socketLive /\ env.session = env.generation /\ t \in Topics
  /\ env' = [env EXCEPT !.enabledGeneration = env.generation,
       !.enabled = @ \cup {t}, !.registry = @ \cup {t}, !.everSubscribed = TRUE]
  /\ UNCHANGED <<policy, queries, obligation, received, execution, coverage, local>>

\* Socket loss and policy fault are observed together. Silent undetected losses
\* and the watchdog that discovers them are explicitly outside this model.
EnvironmentFault == [env EXCEPT !.socketLive = FALSE, !.session = 0,
  !.enabledGeneration = 0, !.enabled = {}, !.generation = @ + 1]
PolicyFault(revoke) == [policy EXCEPT !.generation = @ + 1, !.live = FALSE,
  !.session = 0, !.token = 0, !.connection = TRUE,
  !.revoked = @ \/ revoke,
  !.phase = IF policy.revoked \/ revoke THEN "revoked" ELSE "disconnected"]
Fault(revoke) ==
  /\ env.generation < MaxGeneration /\ ~policy.revoked
  /\ env' = EnvironmentFault /\ policy' = PolicyFault(revoke)
  /\ UNCHANGED <<queries, obligation, received, execution, coverage, local>>

CoverageChange(c) == /\ coverage' = c
  /\ UNCHANGED <<env, policy, queries, obligation, received, execution, local>>
LocalHold(h) == /\ local' = h
  /\ UNCHANGED <<env, policy, queries, obligation, received, execution, coverage>>
StatusFailure == UNCHANGED vars
Idle == UNCHANGED vars

\* Independent obligations are recorded at delivery, even when policy rejects
\* a valid protective envelope. MaxHolds bounds delivered notification holds;
\* Helix-active evidence is separate and never overwrites a raw hold's stamp.
RawMax(highWater, stamp) == IF stamp = Missing THEN highWater ELSE Max(highWater, stamp)
ReplayFloor == Max(StartedAt - 1, env.now - MaxAge)
ReleaseFresh(stamp) == stamp >= StartedAt /\ stamp > ReplayFloor
                       /\ stamp <= env.now + ForwardSkew

\* Evidence for a first stamp is separate from the PRIOR raw high-water snapshot.
Anchor(h,t) == IF t # Missing /\ h.stamp = Missing
                 /\ h.priorHighWater = InitialBarrier /\ h.bootstrapStamp = InitialBarrier
              THEN [h EXCEPT !.bootstrapStamp = t] ELSE h
ObservedHolds(t) == [s \in Sources |-> IF obligation[s] THEN Anchor(env.holds[s],t)
                                                           ELSE env.holds[s]]
ObservedHelix(t) == IF env.helixObserved THEN Anchor(env.helix,t) ELSE env.helix
ObservedPolicy(t) == IF t = Missing THEN policy ELSE [policy EXCEPT
  !.rawHighWater = RawMax(@,t),
  !.chatTime = IF policy.pending.chat THEN Max(@,t) ELSE @,
  !.shieldTime = IF policy.pending.shield THEN Max(@,t) ELSE @,
  !.pending = [s \in Sources |-> FALSE]]
MissingEvidence == [stamp |-> Missing, receipt |-> env.now,
                    priorHighWater |-> env.rawHighWater, bootstrapStamp |-> InitialBarrier]

ProtectiveHoldReceived(source, stamp, origin, admitted, orderTime, observedPolicy) ==
  /\ env.now = LocalNow
  /\ source \in Sources /\ source \notin received /\ stamp \in HoldStamps
  /\ Cardinality(received) < MaxHolds
  /\ origin \in 1..env.generation /\ env.everSubscribed
  /\ received' = received \cup {source}
  /\ obligation' = [obligation EXCEPT ![source] = TRUE]
  /\ env' = [env EXCEPT !.holds = [ObservedHolds(stamp) EXCEPT
                 ![source] = [stamp |-> stamp, receipt |-> env.now,
                              priorHighWater |-> env.rawHighWater,
                              bootstrapStamp |-> InitialBarrier]],
                        !.helix = ObservedHelix(stamp),
                        !.rawHighWater = RawMax(@,stamp),
                        !.shieldTruth = IF source = "shield" THEN TRUE ELSE @]
  /\ policy' = IF ~admitted THEN policy
      ELSE IF source = "chat" THEN [observedPolicy EXCEPT !.chat = TRUE,
              !.chatTime = Max(@,orderTime),
              !.pending.chat = stamp = Missing /\ observedPolicy.rawHighWater = InitialBarrier]
      ELSE [observedPolicy EXCEPT !.shield = TRUE, !.shieldTime = Max(@,orderTime),
              !.revision = @ + 1,
              !.pending.shield = stamp = Missing /\ observedPolicy.rawHighWater = InitialBarrier]
  /\ UNCHANGED <<queries, execution, coverage, local>>

\* Raw Twitch order is independent of local receipt, expiry and policy storage.
\* A missing stamp snapshots the independently observed PRIOR global high water.
\* There is no cap or receipt fallback in this obligation, even before start.
EvidenceNewer(h, stamp) == IF h.stamp # Missing THEN stamp > h.stamp
  ELSE IF h.priorHighWater # InitialBarrier THEN stamp > h.priorHighWater
  ELSE h.bootstrapStamp # InitialBarrier /\ stamp > h.bootstrapStamp
IndependentNewer(source, stamp) ==
  /\ (source \notin received \/ EvidenceNewer(ObservedHolds(stamp)[source],stamp))
  /\ (source # "shield" \/ ~env.helixObserved \/ EvidenceNewer(ObservedHelix(stamp),stamp))

MissingPending(source, p) == p.pending[source]
ReleaseAdmitted(source, stamp, observedPolicy) ==
  /\ ReleaseFresh(stamp)
  /\ ~MissingPending(source, observedPolicy)
  /\ stamp > (IF source = "chat" THEN observedPolicy.chatTime ELSE observedPolicy.shieldTime)

\* Envelopes are well-formed, authorized, unique and current-session, but their
\* timestamps may be OLDER, EQUAL, newer or outside the release skew allowance.
\* Arrival is not conditioned on ReleaseAdmitted or IndependentNewer.
ReleaseReceived(source, stamp, observedPolicy) ==
  /\ env.now = LocalNow + ClockTick
  /\ execution.pc = "idle"
  /\ source \in Sources /\ stamp \in ReleaseStamps
  /\ ActualCurrentChannel /\ policy.live /\ ~policy.revoked /\ policy.phase = "ready"
  /\ obligation' = IF ReleaseFresh(stamp) /\ IndependentNewer(source, stamp)
      THEN [obligation EXCEPT ![source] = FALSE] ELSE obligation
  /\ env' = [env EXCEPT !.rawHighWater = RawMax(@,stamp),
       !.holds = ObservedHolds(stamp), !.helix = ObservedHelix(stamp),
       !.shieldTruth = IF source = "shield" /\ ReleaseFresh(stamp)
                           /\ IndependentNewer(source, stamp) THEN FALSE ELSE @]
  /\ policy' = IF ~ReleaseAdmitted(source, stamp, observedPolicy) THEN observedPolicy
      ELSE IF source = "chat" THEN [observedPolicy EXCEPT !.chat = FALSE, !.chatTime = stamp]
      ELSE [observedPolicy EXCEPT !.shield = FALSE, !.shieldTime = stamp, !.revision = @ + 1]
  /\ UNCHANGED <<queries, received, execution, coverage, local>>

\* Trusted socket metadata can arrive before welcome/subscriptions, in any phase.
\* This is observe_timestamp, including welcome, keepalive and reconnect frames.
ObserveTimestamp(stamp) ==
  /\ stamp \in ObservationStamps /\ stamp \notin env.observations
  /\ env' = [env EXCEPT !.observations = @ \cup {stamp},
                        !.holds = ObservedHolds(stamp), !.helix = ObservedHelix(stamp),
                        !.rawHighWater = RawMax(@,stamp)]
  /\ policy' = ObservedPolicy(stamp)
  /\ UNCHANGED <<queries, obligation, received, execution, coverage, local>>

\* One unnotified activation permits a truthful Helix-active read without begin.
ShieldBecomesActive ==
  /\ ~env.truthRaised
  /\ env' = [env EXCEPT !.truthRaised = TRUE, !.shieldTruth = TRUE]
  /\ UNCHANGED <<policy, queries, obligation, received, execution, coverage, local>>

\* Two local receipt times permit a later delivery with an older remote stamp.
ClockAdvance ==
  /\ env.now = LocalNow /\ env' = [env EXCEPT !.now = @ + ClockTick]
  /\ UNCHANGED <<policy, queries, obligation, received, execution, coverage, local>>

NoLIVEWithoutCurrentChannel == Output = "LIVE" => ActualCurrentChannel
AuthorizedChatHoldPersists == obligation.chat => Output = "HOLD"
AuthorizedShieldBeginPersists == obligation.shield => Output = "HOLD"
RevokedStaysHeld == policy.revoked => Output = "HOLD"
LocalHoldPersists == local => Output = "HOLD"
NoLIVEWithoutCoverage == Output = "LIVE" => coverage
=============================================================================
