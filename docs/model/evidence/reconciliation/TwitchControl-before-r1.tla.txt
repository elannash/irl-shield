--------------------------- MODULE TwitchControl ---------------------------
EXTENDS Integers, Sequences, FiniteSets, TLC
CONSTANTS Capacity, MaxAge, LastClock, MaxGeneration,
          AllowModeratorResume, ForgetOnReconnect, BadCoverage,
          ClobberReconcileRelease
VARIABLES coverage, chat, shield, local, connection, phase, revoked, now,
          seen, floor, chatTime, shieldTime, mode, resumedBy, executed, replayed,
          generation, shieldRevision, snapshot, releaseClobbered
vars == <<coverage, chat, shield, local, connection, phase, revoked, now,
          seen, floor, chatTime, shieldTime, mode, resumedBy, executed, replayed,
          generation, shieldRevision, snapshot, releaseClobbered>>
history == <<seen, floor, chatTime, shieldTime, resumedBy, executed, replayed>>
query == <<generation, shieldRevision, snapshot, releaseClobbered>>

\* One immutable envelope per ID. Re-delivery preserves its payload/timestamp.
Messages == {"hold", "ownerResume", "modResume", "shieldBegin", "shieldEnd", "viewerHold"}
Stamp(m) == CASE m = "hold" -> 1
             [] m \in {"ownerResume", "shieldBegin"} -> 2
             [] OTHER -> 3
Actor(m) == CASE m = "ownerResume" -> "owner"
             [] m = "viewerHold" -> "viewer"
             [] OTHER -> "moderator"
IsChat(m) == m \notin {"shieldBegin", "shieldEnd"}
Max(a,b) == IF a > b THEN a ELSE b
Members(s) == {s[i]: i \in 1..Len(s)}
Settle(c,h,s,l,n) == IF h \/ s \/ l \/ n THEN "HOLD"
                     ELSE IF c \/ BadCoverage THEN "LIVE" ELSE "PROTECT"

\* Starts immediately after constructing Control and ShieldEvents.
Init == /\ coverage = FALSE /\ chat = FALSE /\ shield = FALSE /\ local = FALSE
        /\ connection = TRUE /\ phase = "connecting" /\ revoked = FALSE /\ now = 1
        /\ seen = <<>> /\ floor = 0 /\ chatTime = 0 /\ shieldTime = 0
        /\ mode = "HOLD" /\ resumedBy = "none" /\ executed = {} /\ replayed = FALSE
        /\ generation = 0 /\ shieldRevision = 0 /\ snapshot = <<>>
        /\ releaseClobbered = FALSE

Coverage(c) == /\ coverage' = c /\ mode' = Settle(c,chat,shield,local,connection)
               /\ UNCHANGED <<chat,shield,local,connection,phase,revoked,now,history,query>>
LocalHold(h) == /\ local' = h /\ mode' = Settle(coverage,chat,shield,h,connection)
                /\ UNCHANGED <<coverage,chat,shield,connection,phase,revoked,now,history,query>>
Welcome == /\ ~revoked /\ phase' = "subscribing"
           /\ UNCHANGED <<coverage,chat,shield,local,connection,revoked,now,history,mode,query>>
\* Approved planned migration never asserts a new connection hold.
Reconnect == /\ phase' = IF phase = "ready" THEN "handover" ELSE phase
             /\ seen' = IF ForgetOnReconnect THEN <<>> ELSE seen
             /\ floor' = IF ForgetOnReconnect THEN 0 ELSE floor
             /\ UNCHANGED <<coverage,chat,shield,local,connection,revoked,now,
                            chatTime,shieldTime,mode,resumedBy,executed,replayed,query>>
HandedOver == /\ phase = "handover" /\ ~revoked /\ phase' = "ready"
              /\ UNCHANGED <<coverage,chat,shield,local,connection,revoked,now,history,mode,query>>
Fault(r) == /\ generation < MaxGeneration /\ generation' = generation + 1
            /\ revoked' = (revoked \/ r)
            /\ phase' = IF revoked' THEN "revoked" ELSE "disconnected"
            /\ connection' = TRUE /\ mode' = "HOLD"
            /\ UNCHANGED <<coverage,chat,shield,local,now,history,shieldRevision,snapshot,releaseClobbered>>
\* Keep one environment-owned returned token. A later call may discard its new
\* token and retain the old one, allowing stale completion after a fresh begin.
BeginReconcile(save) ==
  /\ ~revoked /\ phase' = "reconciling" /\ connection' = TRUE /\ mode' = "HOLD"
  /\ snapshot' = IF save \/ snapshot = <<>> THEN <<generation,shieldRevision>> ELSE snapshot
  /\ UNCHANGED <<coverage,chat,shield,local,revoked,now,history,generation,shieldRevision,releaseClobbered>>
ReconciliationCurrent == IF snapshot = <<>> THEN FALSE
                         ELSE ~revoked /\ phase = "reconciling" /\ snapshot[1] = generation
\* A failed HTTP/status parse or a non-boolean result cannot release anything.
\* Retry waits 1,2,4,8,16,30,30,... are collapsed to stuttering: no policy write.
StatusFailure == /\ ReconciliationCurrent /\ UNCHANGED vars
RejectedCompletion == /\ ~ReconciliationCurrent /\ UNCHANGED vars
Reconciled(active) ==
  LET expectedShield == IF snapshot[2] = shieldRevision THEN active ELSE shield
      newChat == IF ClobberReconcileRelease THEN FALSE ELSE chat
      newLocal == IF ClobberReconcileRelease THEN FALSE ELSE local
      newShield == IF ClobberReconcileRelease THEN FALSE ELSE expectedShield
  IN /\ ReconciliationCurrent
     /\ chat' = newChat /\ local' = newLocal /\ shield' = newShield
     /\ connection' = FALSE /\ phase' = "ready"
     /\ mode' = Settle(coverage,newChat,newShield,newLocal,FALSE)
     /\ releaseClobbered' = (releaseClobbered \/ newChat # chat \/ newLocal # local
                             \/ newShield # expectedShield)
     /\ UNCHANGED <<coverage,revoked,now,history,generation,shieldRevision,snapshot>>
Tick == /\ now < LastClock /\ now' = now + 1
        /\ UNCHANGED <<coverage,chat,shield,local,connection,phase,revoked,history,mode,query>>

\* Purge precedes envelope validation; eviction precedes command authorization.
Deliver(m, valid, sourceLocal) ==
  LET agedFloor == Max(floor, now - MaxAge)
      agedSeen == SelectSeq(seen, LAMBDA id: Stamp(id) > agedFloor)
      admitted == valid /\ Stamp(m) > agedFloor /\ Stamp(m) <= now
                  /\ m \notin Members(agedSeen)
      evict == admitted /\ Len(agedSeen) >= Capacity
      newFloor == IF evict THEN Max(agedFloor,Stamp(Head(agedSeen))) ELSE agedFloor
      rest == IF evict THEN Tail(agedSeen) ELSE agedSeen
      remembered == admitted /\ Stamp(m) > newFloor
      chatOK == remembered /\ IsChat(m) /\ sourceLocal
      hold == chatOK /\ m \in {"hold", "viewerHold"}
              /\ Actor(m) \in {"owner", "moderator"}
      resume == chatOK /\ m \in {"ownerResume", "modResume"}
                /\ (Actor(m) = "owner" \/ AllowModeratorResume)
                /\ Stamp(m) > chatTime
      shieldOK == remembered /\ ~IsChat(m) /\ Stamp(m) >= shieldTime
                  /\ (m = "shieldBegin" \/ Stamp(m) > shieldTime)
      command == hold \/ resume \/ shieldOK
      newChat == IF hold THEN TRUE ELSE IF resume THEN FALSE ELSE chat
      newShield == IF shieldOK THEN m = "shieldBegin" ELSE shield
  IN /\ phase \in {"ready", "handover", "reconciling"} /\ m \in Messages
     /\ floor' = newFloor /\ seen' = IF remembered THEN Append(rest,m) ELSE rest
     /\ chat' = newChat /\ shield' = newShield
     /\ chatTime' = IF hold THEN Max(chatTime,Stamp(m)) ELSE IF resume THEN Stamp(m) ELSE chatTime
     /\ shieldTime' = IF shieldOK THEN Stamp(m) ELSE shieldTime
     /\ shieldRevision' = IF shieldOK THEN shieldRevision + 1 ELSE shieldRevision
     /\ resumedBy' = IF resume THEN Actor(m) ELSE resumedBy
     /\ executed' = IF command THEN executed \cup {m} ELSE executed
     /\ replayed' = (replayed \/ (command /\ m \in executed))
     /\ mode' = Settle(coverage,newChat,newShield,local,connection)
     /\ UNCHANGED <<coverage,local,connection,phase,revoked,now,generation,snapshot,releaseClobbered>>

Idle == UNCHANGED vars
Next == (\E c \in BOOLEAN: Coverage(c)) \/ (\E h \in BOOLEAN: LocalHold(h))
        \/ Welcome \/ Reconnect \/ HandedOver \/ (\E r \in BOOLEAN: Fault(r))
        \/ (\E save \in BOOLEAN: BeginReconcile(save))
        \/ (\E active \in BOOLEAN: Reconciled(active))
        \/ StatusFailure \/ RejectedCompletion \/ Tick
        \/ (\E m \in Messages, v \in BOOLEAN, s \in BOOLEAN: Deliver(m,v,s)) \/ Idle
NoLIVEWithoutCoverage == mode = "LIVE" => coverage /\ ~chat /\ ~shield /\ ~local /\ ~connection
OnlyBroadcasterResumes == resumedBy \in {"none", "owner"}
ReconnectNeverReplays == ~replayed
BoundedMemory == Len(seen) <= Capacity
ReconcileReleaseIsolated == ~releaseClobbered
ReconcileWaitHolds == phase = "reconciling" => connection /\ mode = "HOLD"
ReadyAndHandoverHaveNoConnectionHold == phase \in {"ready", "handover"} => ~connection
RevokedStaysHeld == revoked => connection /\ mode = "HOLD"
Spec == Init /\ [][Next]_vars
=============================================================================
