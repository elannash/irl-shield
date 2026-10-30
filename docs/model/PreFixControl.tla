--------------------------- MODULE PreFixControl ---------------------------
EXTENDS ControlEnvironment
\* Projection of bb6948b's actual API; no mutation/defect switches.
Init == EnvironmentInit /\ policy = InitialPolicy(0)
NewConnection ==
  /\ ~env.socketLive /\ ~policy.revoked /\ env.generation < MaxGeneration
  /\ env' = [env EXCEPT !.generation = @ + 1, !.socketLive = TRUE]
  /\ UNCHANGED <<policy, queries, obligation, received, execution, coverage, local>>
Welcome(g) ==
  /\ g \in env.queuedWelcome
  /\ env' = [env EXCEPT !.queuedWelcome = @ \ {g}, !.callbackOrigin = g]
  /\ policy' = IF policy.revoked THEN policy
      ELSE [policy EXCEPT !.session = g, !.phase = "subscribing"]
  /\ UNCHANGED <<queries, obligation, received, execution, coverage, local>>
BeginReconcile ==
  /\ ~policy.revoked /\ env.callbackOrigin # 0 /\ env.registry = Topics
  /\ Len(queries) < MaxQueries /\ execution.pc = "idle"
  /\ queries' = Append(queries, [generation |-> policy.generation,
        revision |-> policy.revision, session |-> policy.session, active |-> env.shieldTruth])
  /\ policy' = [policy EXCEPT !.phase = "reconciling", !.connection = TRUE]
  /\ env' = [env EXCEPT !.callbackOrigin = 0]
  /\ UNCHANGED <<obligation, received, execution, coverage, local>>
Current(q) == ~policy.revoked /\ policy.phase = "reconciling"
              /\ queries[q].generation = policy.generation
OldFault(revoke) ==
  /\ env.generation < MaxGeneration /\ ~policy.revoked
  /\ env' = EnvironmentFault
  /\ policy' = [policy EXCEPT !.generation = @ + 1, !.connection = TRUE,
       !.revoked = @ \/ revoke,
       !.phase = IF policy.revoked \/ revoke THEN "revoked" ELSE "disconnected"]
  /\ UNCHANGED <<queries, obligation, received, execution, coverage, local>>
Reconciled(q) ==
  /\ q \in 1..Len(queries) /\ Current(q)
  /\ policy' = [policy EXCEPT !.phase = "ready", !.connection = FALSE,
      !.shield = IF queries[q].revision = policy.revision THEN queries[q].active ELSE @]
  /\ UNCHANGED <<env, queries, obligation, received, execution, coverage, local>>
DeliverHold(s,t,g) == ProtectiveHoldReceived(s,t,g,
  policy.phase \in {"ready", "handover", "reconciling"} /\ t >= 0 /\ t <= LocalNow, t)
\* Old API has no generation input; live is unused except for shared releases.
\* Release scenarios are omitted in the old failure configurations (below).
Next == QueueWelcome \/ (\E t \in Topics: EnableSubscription(t))
  \/ NewConnection \/ (\E g \in env.queuedWelcome: Welcome(g))
  \/ (\E r \in BOOLEAN: OldFault(r)) \/ BeginReconcile
  \/ (\E q \in 1..Len(queries): Reconciled(q))
  \/ (\E s \in Sources, t \in HoldStamps, g \in 1..env.generation: DeliverHold(s,t,g))
  \/ (\E c \in BOOLEAN: CoverageChange(c)) \/ (\E h \in BOOLEAN: LocalHold(h))
  \/ StatusFailure \/ Idle
Spec == Init /\ [][Next]_vars
=============================================================================
