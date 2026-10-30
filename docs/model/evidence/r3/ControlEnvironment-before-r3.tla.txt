------------------------- MODULE ControlEnvironment -------------------------
EXTENDS Integers, Sequences, FiniteSets, TLC
CONSTANTS MaxGeneration, MaxQueries, HoldStamps, ReleaseStamps, LocalNow,
          StartedAt, Missing
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
             shieldTruth |-> FALSE, now |-> LocalNow,
             holds |-> [s \in Sources |-> [stamp |-> Missing, receipt |-> 0]]]
  /\ queries = <<>> /\ obligation = [chat |-> FALSE, shield |-> FALSE]
  /\ received = {} /\ execution = [pc |-> "idle", token |-> 0]
  /\ coverage = TRUE /\ local = FALSE

\* Init is after opening the first socket (connection_started in fixed code),
\* before its welcome. Session IDs are represented by their connection origin.
InitialPolicy(g) == [generation |-> g, live |-> FALSE, session |-> 0,
  phase |-> "connecting", revoked |-> FALSE, connection |-> TRUE,
  guard |-> FALSE, chat |-> FALSE, shield |-> FALSE,
  revision |-> 0, chatTime |-> -1, shieldTime |-> -1, token |-> 0]

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
\* a valid protective envelope. One unique chat hold and Shield begin are enough
\* for these counterexamples; deduplication/cache bounds are not abstract proofs.
ProtectiveHoldReceived(source, stamp, origin, admitted, orderTime) ==
  /\ env.now = LocalNow
  /\ source \in Sources /\ source \notin received /\ stamp \in HoldStamps
  /\ origin \in 1..env.generation /\ env.everSubscribed
  /\ received' = received \cup {source}
  /\ obligation' = [obligation EXCEPT ![source] = TRUE]
  /\ env' = [env EXCEPT !.holds[source] = [stamp |-> stamp, receipt |-> env.now],
                        !.shieldTruth = IF source = "shield" THEN TRUE ELSE @]
  /\ policy' = IF ~admitted THEN policy
      ELSE IF source = "chat" THEN [policy EXCEPT !.chat = TRUE,
                                                  !.chatTime = Max(@,orderTime)]
      ELSE [policy EXCEPT !.shield = TRUE, !.shieldTime = Max(@,orderTime),
                           !.revision = @ + 1]
  /\ UNCHANGED <<queries, execution, coverage, local>>

\* The evidence above retains the raw Twitch stamp AND local receipt. A bounded
\* valid stamp is discharged strictly by Twitch order, never by policy's key.
\* Missing/pre-start stamps have no usable remote order: require newer receipt.
\* Pathological >+30 stamps have only a capped protective obligation, by design;
\* they do NOT assert that all releases before their raw remote stamp are unsafe.
IndependentNewer(source, stamp) ==
  LET h == env.holds[source]
  IN IF h.stamp = Missing THEN stamp > h.receipt
     ELSE IF h.stamp < StartedAt THEN stamp > h.receipt
     ELSE IF h.stamp <= h.receipt + 30 THEN stamp > h.stamp
     ELSE stamp > h.receipt + 30

ReleaseAdmitted(source, stamp) ==
  /\ stamp >= StartedAt /\ stamp <= env.now + 30
  /\ stamp > (IF source = "chat" THEN policy.chatTime ELSE policy.shieldTime)

\* Envelopes are well-formed, authorized, unique and current-session, but their
\* timestamps may be OLDER, EQUAL, newer or outside the release skew allowance.
\* Arrival is not conditioned on ReleaseAdmitted or IndependentNewer.
ReleaseReceived(source, stamp) ==
  /\ env.now = LocalNow + 1
  /\ execution.pc = "idle"
  /\ source \in Sources /\ stamp \in ReleaseStamps
  /\ ActualCurrentChannel /\ policy.live /\ ~policy.revoked /\ policy.phase = "ready"
  /\ obligation' = IF stamp >= StartedAt /\ stamp <= env.now + 30
                      /\ IndependentNewer(source, stamp)
      THEN [obligation EXCEPT ![source] = FALSE] ELSE obligation
  /\ env' = IF source = "shield" /\ stamp >= StartedAt
                 /\ stamp <= env.now + 30 /\ IndependentNewer(source, stamp)
      THEN [env EXCEPT !.shieldTruth = FALSE] ELSE env
  /\ policy' = IF ~ReleaseAdmitted(source, stamp) THEN policy
      ELSE IF source = "chat" THEN [policy EXCEPT !.chat = FALSE, !.chatTime = stamp]
      ELSE [policy EXCEPT !.shield = FALSE, !.shieldTime = stamp, !.revision = @ + 1]
  /\ UNCHANGED <<queries, received, execution, coverage, local>>

\* Two local receipt times permit a later delivery with an older remote stamp.
ClockAdvance ==
  /\ env.now = LocalNow /\ env' = [env EXCEPT !.now = @ + 1]
  /\ UNCHANGED <<policy, queries, obligation, received, execution, coverage, local>>

NoLIVEWithoutCurrentChannel == Output = "LIVE" => ActualCurrentChannel
AuthorizedChatHoldPersists == obligation.chat => Output = "HOLD"
AuthorizedShieldBeginPersists == obligation.shield => Output = "HOLD"
RevokedStaysHeld == policy.revoked => Output = "HOLD"
LocalHoldPersists == local => Output = "HOLD"
NoLIVEWithoutCoverage == Output = "LIVE" => coverage
=============================================================================
