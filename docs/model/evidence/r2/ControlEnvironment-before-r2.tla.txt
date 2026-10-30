------------------------- MODULE ControlEnvironment -------------------------
EXTENDS Integers, Sequences, FiniteSets, TLC
CONSTANTS MaxGeneration, MaxQueries, HoldStamps, LocalNow
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
             shieldTruth |-> FALSE]
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
  /\ source \in Sources /\ source \notin received /\ stamp \in HoldStamps
  /\ origin \in 1..env.generation /\ env.everSubscribed
  /\ received' = received \cup {source}
  /\ obligation' = [obligation EXCEPT ![source] = TRUE]
  /\ env' = IF source = "shield" THEN [env EXCEPT !.shieldTruth = TRUE] ELSE env
  /\ policy' = IF ~admitted THEN policy
      ELSE IF source = "chat" THEN [policy EXCEPT !.chat = TRUE,
                                                  !.chatTime = Max(@,orderTime)]
      ELSE [policy EXCEPT !.shield = TRUE, !.shieldTime = Max(@,orderTime),
                           !.revision = @ + 1]
  /\ UNCHANGED <<queries, execution, coverage, local>>

\* All modeled releases are fresh, well-formed, owner-authorized and from the
\* live current generation. Rejected/malformed/viewer releases stutter; parsing,
\* authorization and replay-cache internals are verified by concrete tests only.
LegitimateRelease(source, stamp) ==
  /\ source \in Sources /\ stamp \in {LocalNow + 1, LocalNow + 30}
  /\ ActualCurrentChannel /\ policy.live /\ ~policy.revoked /\ policy.phase = "ready"
  /\ stamp > (IF source = "chat" THEN policy.chatTime ELSE policy.shieldTime)
  /\ obligation' = [obligation EXCEPT ![source] = FALSE]
  /\ env' = IF source = "shield" THEN [env EXCEPT !.shieldTruth = FALSE] ELSE env
  /\ policy' = IF source = "chat" THEN [policy EXCEPT !.chat = FALSE, !.chatTime = stamp]
      ELSE [policy EXCEPT !.shield = FALSE, !.shieldTime = stamp, !.revision = @ + 1]
  /\ UNCHANGED <<queries, received, execution, coverage, local>>

NoLIVEWithoutCurrentChannel == Output = "LIVE" => ActualCurrentChannel
AuthorizedChatHoldPersists == obligation.chat => Output = "HOLD"
AuthorizedShieldBeginPersists == obligation.shield => Output = "HOLD"
RevokedStaysHeld == policy.revoked => Output = "HOLD"
LocalHoldPersists == local => Output = "HOLD"
NoLIVEWithoutCoverage == Output = "LIVE" => coverage
=============================================================================
