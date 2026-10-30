--------------------------- MODULE TwitchControl ---------------------------
EXTENDS ControlEnvironment
\* Policy source: 907a17f8; no production mutation flags.
Init == EnvironmentInit /\ policy = InitialPolicy(1)
NewConnection ==
  /\ execution.pc = "idle" /\ ~env.socketLive /\ ~policy.revoked
  /\ env.generation < MaxGeneration
  /\ env' = [env EXCEPT !.generation = @ + 1, !.socketLive = TRUE, !.registry = {}]
  /\ policy' = [PolicyFault(FALSE) EXCEPT !.phase = "connecting"]
  /\ UNCHANGED <<queries, obligation, received, execution, coverage, local>>
Welcome(g) ==
  LET accepted == g = policy.generation /\ ~policy.revoked /\ policy.phase = "connecting"
  IN /\ execution.pc = "idle" /\ g \in env.queuedWelcome
     /\ env' = [env EXCEPT !.queuedWelcome = @ \ {g},
                            !.callbackOrigin = IF accepted THEN g ELSE @]
     /\ policy' = IF accepted THEN [policy EXCEPT !.session = g, !.live = TRUE,
                                                   !.phase = "subscribing"] ELSE policy
     /\ UNCHANGED <<queries, obligation, received, execution, coverage, local>>

\* Transport admits reconciliation only after all enabled responses match the
\* actual welcomed session. HTTP validation is a source-mapped assumption here.
BeginReconcile ==
  /\ execution.pc = "idle" /\ Len(queries) < MaxQueries
  /\ ActualCurrentChannel /\ env.generation = policy.generation
  /\ policy.live /\ ~policy.revoked
  /\ policy.phase \in {"subscribing", "ready", "reconciling"}
  /\ queries' = Append(queries, [generation |-> policy.generation,
        revision |-> policy.revision, session |-> policy.session, active |-> env.shieldTruth])
  /\ policy' = [policy EXCEPT !.phase = "reconciling", !.connection = TRUE,
                               !.guard = TRUE, !.token = Len(queries) + 1]
  /\ env' = [env EXCEPT !.callbackOrigin = 0]
  /\ UNCHANGED <<obligation, received, execution, coverage, local>>
Current(q) == q = policy.token /\ ~policy.revoked /\ policy.live
  /\ policy.phase = "reconciling" /\ queries[q].generation = policy.generation
  /\ queries[q].session = policy.session

\* q is object identity: equal snapshot fields do not make an old object current.
StartCompletion(q) ==
  /\ execution.pc = "idle" /\ q \in 1..Len(queries) /\ Current(q)
  /\ execution' = [pc |-> "statusCallback", token |-> q,
                    applyStatus |-> queries[q].revision = policy.revision]
  /\ UNCHANGED <<env, policy, queries, obligation, received, coverage, local>>
\* The branch was decided before entering the callback. A reentrant begin can
\* change revision, then the callback still applies the older FALSE afterward.
ApplyStatus ==
  /\ execution.pc = "statusCallback"
  /\ policy' = [policy EXCEPT !.shield =
       IF execution.applyStatus THEN queries[execution.token].active ELSE @]
  /\ execution' = [execution EXCEPT !.pc = "statusCheck"]
  /\ UNCHANGED <<env, queries, obligation, received, coverage, local>>
CheckStatus ==
  /\ execution.pc = "statusCheck"
  /\ policy' = IF Current(execution.token) /\ execution.applyStatus
       /\ ~queries[execution.token].active
       /\ queries[execution.token].revision # policy.revision
       THEN [policy EXCEPT !.shield = TRUE] ELSE policy
  /\ execution' = [execution EXCEPT !.pc =
       IF Current(execution.token) THEN "connectionCallback" ELSE "idle"]
  /\ UNCHANGED <<env, queries, obligation, received, coverage, local>>
\* Reentry may fault before the callback applies FALSE. It must still apply
\* FALSE after the fault; the separate guard must prevent intermediate LIVE.
ApplyConnectionRelease ==
  /\ execution.pc = "connectionCallback"
  /\ policy' = [policy EXCEPT !.connection = FALSE]
  /\ execution' = [execution EXCEPT !.pc = "connectionCheck"]
  /\ UNCHANGED <<env, queries, obligation, received, coverage, local>>
CheckConnection ==
  /\ execution.pc = "connectionCheck"
  /\ policy' = IF Current(execution.token) THEN [policy EXCEPT !.phase = "ready"] ELSE policy
  /\ execution' = [execution EXCEPT !.pc =
       IF Current(execution.token) THEN "guardCallback" ELSE "idle"]
  /\ UNCHANGED <<env, queries, obligation, received, coverage, local>>
ApplyGuardRelease ==
  /\ execution.pc = "guardCallback"
  /\ policy' = [policy EXCEPT !.guard = FALSE]
  /\ execution' = [execution EXCEPT !.pc = "finish"]
  /\ UNCHANGED <<env, queries, obligation, received, coverage, local>>
FinishCompletion ==
  /\ execution.pc = "finish"
  /\ policy' = IF execution.token = policy.token /\ policy.live /\ ~policy.revoked
                    /\ policy.phase = "ready"
      THEN [policy EXCEPT !.token = 0] ELSE policy
  /\ execution' = [execution EXCEPT !.pc = "idle"]
  /\ UNCHANGED <<env, queries, obligation, received, coverage, local>>

\* Admission is independent of phase, origin generation and remote timestamp.
\* 0 represents pre-start/expired/unparseable stamps ordered at receipt.
OrderTime(t) == IF t = 0 THEN LocalNow ELSE Min(t, LocalNow)
DeliverHold(s,t,g) == ProtectiveHoldReceived(s,t,g,TRUE,OrderTime(t))
Reconnect ==
  /\ execution.pc = "idle" /\ policy.live /\ ~policy.revoked /\ policy.phase = "ready"
  /\ policy' = [policy EXCEPT !.phase = "handover"]
  /\ UNCHANGED <<env, queries, obligation, received, execution, coverage, local>>
HandedOver ==
  /\ execution.pc = "idle" /\ policy.phase = "handover" /\ policy.live /\ ~policy.revoked
  /\ env.socketLive /\ env.session = env.generation
  /\ env' = [env EXCEPT !.session = env.generation + 10]
  /\ policy' = [policy EXCEPT !.session = env.generation + 10, !.phase = "ready"]
  /\ UNCHANGED <<queries, obligation, received, execution, coverage, local>>

Next == QueueWelcome \/ (\E t \in Topics: EnableSubscription(t)) \/ NewConnection
  \/ (\E g \in env.queuedWelcome: Welcome(g)) \/ (\E r \in BOOLEAN: Fault(r))
  \/ BeginReconcile \/ (\E q \in 1..Len(queries): StartCompletion(q))
  \/ ApplyStatus \/ CheckStatus \/ ApplyConnectionRelease \/ CheckConnection
  \/ ApplyGuardRelease \/ FinishCompletion
  \/ (\E s \in Sources, t \in HoldStamps, g \in 1..env.generation: DeliverHold(s,t,g))
  \/ (\E s \in Sources, t \in {LocalNow + 1, LocalNow + 30}: LegitimateRelease(s,t))
  \/ Reconnect \/ HandedOver
  \/ (\E c \in BOOLEAN: CoverageChange(c)) \/ (\E h \in BOOLEAN: LocalHold(h))
  \/ StatusFailure \/ Idle
Spec == Init /\ [][Next]_vars
=============================================================================
