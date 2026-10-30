# M2 implementation ledger

Original start about 2026-10-30 03:55 UTC; original eight-hour timebox and Friday07AMPT deadline retained. Base ec1d1f96a1c29ab82109c66f27064f3fd6cb326d. No stage/commit/push.

## 2026-10-30 04:07 UTC

Verified clean isolated prepared worktree and exact base. Renamed branch t3/m2-relay to elannash/m2-relay in place. Loaded codebase-design,TDD,test-review gate,research,diagnosing-bugs,receipt-audit,resume-note guidance. No outside project code imported.

Added draft restricted MediaMTX/auth,persistent RelaySession/runtime and bounded decoder/encoder in owned paths. Installed PyAV16.0.1 in owned .tmp/m2/py311 with readonly rootGPU site .pth. Initial Python3.14 environment unsuitable for root3.11 binary libraries,retained unused. No global packages/system CUDA change.

MediaMTX v1.21.3 MIT archive SHA256 0a2ea7eba96023631efa1bea7804823a9145b043b6646a8a05798d4ac24ed635; binary bfa372a169751bbf6da2ebddcbcd2f7d3ab3dca3cc553022162eda36fe03e73d. Sources/license snapshot .tmp/m2/source; .tmp/m2/tools.log.

Receipts /tmp/agents/irl-shield/m2-relay/01-* through10-*. Security2tests pass; live1test passes. Initial live assertion incorrectly assumed unlimited poll; adjusted to multiple controlled ticks because engine cap4outputs/poll. Native auth first exposed unsupported MediaMTX collection env overrides; paths/users moved to scoped stdin JSON. Final10-auth-loopback.json: anonymous/bad publisher rejected,phone denied shielded,validphone camera and internal shielded accepted; owned sockets exactlyTCP127.0.0.1:19350 andUDP127.0.0.1:18890; serverexit0. RTMP ACL proof only,not SRT/egress/quality.

No GPU/inference/soak/timed/OCR run. Root queue sealed,fresh timedqueue and corrected independent judges pending. Old pooled scorecards ineligible.

Three owner-authorized Ultra/priority Codex children in isolated T3 worktrees; original deadlines/no commits/no heavyjobs:
- Ingest: relay/security.py,mediamtx.py,native_auth.py; scripts/m2-tools,m2-native; tests/m2/test_security.py; relay/INGEST-HANDBACK.md. Testbudget6.
- Egress/audio: relay/stream.py; tests/m2/test_stream.py; relay/EGRESS-HANDBACK.md. Testbudget6.
- Gate2: relay/soak.py,fixture.py,seal.py; scripts/m2-soak; tests/m2/test_seal.py; relay/GATE2-HANDBACK.md. Testbudget6.

Parent retains runtime/control integration,README,fullgate,native execution,audit/final handback. Initial parent suite/probe invocations10;children18;parentreserve12. Ad-hoc diagnostic commands also in toolhistory for final ledger.

Live state: three authorized childtasks only. All initial MediaMTX processes exited. No retained port/media process.

## 2026-10-30 04:21 UTC — ingest acceptance and native RTMP investigation

Read every ingest deliverable and both final native receipts; copied seven owned files only. Source SHA256 matched the child's source.sha256. Accepted child-owned listener startup regression, restricted bind proof, scoped stdin config and SRT auth/three-packet reads on both hosts. RTMP original positive reads remain a failed claim; final assertion-only child test delta awaits parent gate. Receipt audit snapshot: .tmp/m2/parent-audit.json.

Added parent single-writer AST guard; a deliberate decoded-frame output route fails with exactly “A decoded-frame or secondary sink route bypasses the engine”; restored relay/live.py byte-for-byte and reran green. Receipts13-single-writer-red.log/14-single-writer-green.log plus13-single-writer-mutation.diff.

Parent native follow-up11 segfaulted with no JSON. Narrow12 RTMP read returned OSError errno5. Redacted in-memory server15 diagnostic established no stream available on camera before track registration. Primary gortmplib reader source analyzes two seconds of DTS before AddPublisher; publisher readiness now waits for2.1seconds DTS rather than first mux. Native16 and narrow17 segfault on av.open after allowing track registration;17 faulthandler identifies client av.open while publisher is paced. No successful RTMP media-read claim yet. Cores disabled before credentials; apport directory contained no new lane report, and no MediaMTX survivor was observed after first crash. Probe18 tests supported PyAV set_level(None), which completely disables its Python log callback; -8 suppresses display but still processes errors in callback. This is a falsifiable crash hypothesis, not an accepted cause until18 passes.

Added Linux setup/read-only GPU reuse recipe and relay README/M3 callbacks. No detector changes, GPU/native encoder, soak, OCR grading or Twitch connection. Fresh root timed queue still pending. Children egress/audio and Gate2 harness not yet accepted. Parent suite/probe numbered invocations now18 including failures; child ingest6. Ad-hoc initial capability/diagnostic calls will be disclosed separately; original40 cap remains.

## 2026-10-30 04:26 UTC — cross-protocol reader

Probe18 falsified the logging-callback crash hypothesis. GDB19 identifies av_dict_free inside PyAV16 InputContainer.__cinit__ after find_stream_info. Installed input.pyx allocates its stream-option dictionary array using initial nb_streams and frees using the later count; dynamic RTMP discovery plus general options is my inferred upstream cause. No library patched. Backtrace arguments suppressed to avoid credentials.

Conductor authorized testing MediaMTX protocol conversion instead. Probe20: RTMP publication -> loopback RTSP/TCP successfully opened a video track and decoded3actual frames (76source packets sent). SRT immediate RTSP read got404afteronepacket, before track registration; that subcase remains red pending bounded path-readiness retry. No AV proof because source contains no audio. Adopted one RTSP/TCP internal reader interface; final integrated tests still pending. Added explicit authenticated loopback RTSP listener and tcp-only transport; existing RTMP/SRT publish credentials unchanged. Exact new socket ACL/protocol matrix awaits parent gate. Root instruction remains stop/report if actual available RTSP path crashes; no crashing-decoder workarounds.

Parent budget: numbered20 invocations; ingest child6. Two remaining child test counts await handbacks. Preserve fullgate/queuednative budget from unused child allocations. No GPU/heavyjob has run. No scorecard/privacy result.

## 2026-10-30 04:31 UTC — affected suite, functional gate, queued acceptance

All three child hand-backs read in full, source hashes matched before copy, and claimed test logs inspected. Child egress accepted only provisionally: its finaltwo errors were reproduced in local39. NativeFFmpeg40 reports dimensions not set: networkdecoder template0x0, soleencoder64x32. Fixed negotiatedshape.41 then passed egress lifecycle but failed packetidentity(AnnexBprefix versusAVCClengthprefix) and the new staleaudio regression. FFmpeg8flvenc.c1303–1306 confirms extradata selects AnnexBconversion. Retained originalencoderextradata for networkdecoder template; clearedaudio tags ondisconnect/newgeneration.42 all16M2tests passed, including packet/header/keyframeidentity,AACflush,fileflash/beep,stallreap,queueinvalidation,staleaudio. FullLinuxgate43:96defaulttests+16M2tests+compileall pass. MacSwift check unavailableonLinux; no fullcross-platformgate claim.

Conductor raised ceiling40->52 withouttimeboxreset. Invocations38through43 include18childcalls+parentnumbered01..20 then39..43. Currentexecuted43; next3native producers queued(noresultyet), autoattempts countwhenexecuted.

Integrated one internalRTSP/TCP camera read; authenticatedloopback18554explicitlistener, RTMP/SRTphonepublishpathsunchanged. Capture nowreadsRTSP/TCP andnativeSRT via existinglibsrt, without crashing directRTMP decoder. Both publishers andcapture useopaque decoder templates forcopy, preservekeyframeflags. Added SRTsender mode. Sender sourceaudio discarded/generatedtoneonly. Noengine/scorer/cache/rootrequirements/rootREADME touched. Sourcefrozen afterqueue submission; docs only maychange.

Freshcentralqueue /home/elan/code/irl-shield/.tmp/irl-shield-builder-m2-queue-1 submitted3jobsandSEALED:
- m2-rtmp-av359c4d901f1a4d35b5152a7132be0a0b:30sec RTMPpublish,RTSP+SRTcapture.
- m2-srt-av ecab6ba5f532409291ee08a32cbe7a8f:30sec SRTpublish,RTSP+SRTcapture.
- m2-soak b33563fb522d46bbb49dd4c6d6a302f8:1200sec RTMPpublish,RTSP+SRTcapture,faultinjection.

Exactargv andenv(nonsecret librarypaths/workerlimits) .tmp/m2/queue-producers.json; enqueue/sealreceipts /tmp/agents/irl-shield/m2-relay/*enqueue.json andm2-queue-sealed.json. InheritedEXlease validated byharness,no nestedflock. Rootownsrunner3141521 andstop. Jobsqueued,notnativepass; artifacts .tmp/m2/gate2/<job>/attempt-N. IndependentOCRaftercorrectedPR1merge pending. Qnotqualified,allfixturederivativesbenchmark-only/no music/notdemoready. NoTwitchconnectionorcredentialsretrieved. No sourcecommit/stage/push.

Corrected ownedrelay docs' PyAVwheel license statement: wheelcontainslibx264; LGPL-onlydescription insufficient. PyAV BSD-3-Clause plusFFmpeg GPL/componentnotices; rootrequirementslicenseintegration remainsrootowned. No newbinaryredistribution.

## 2026-10-30 05:38 UTC — sealed native failure diagnosis

Conductor reports both uncontended A/V jobs failed decoded-analysis; soak1 failed runtime undercontention; soak2 pre-exec rejected; soak3 running. No requeue performed. Original source remains frozen; fixes staged onlyin.tmp/m2/fixes.

Read both A/V events/runtime/frame/sender/failure/capture receipts. RTSP native captures contain actualdecoded A/V: SRTpublication1014frames/33.784s,RTMPpublication1015frames/33.819s; monotonicPTS and flash/beep pairs exist. Their optionalSRTcapture wrotezero-byteMatroska files and stoppedonfirstAACpacket.44 locallyreproduces InvalidDataError onboth emptyfiles.45 recreates realSRTsocketcopy and traces the firstnativeerror safely: ValueError(errno22) atCapture.output.mux; video templatewidth0,height0,extradata0; audiotemplateextradata0. Publisherclean,ownedMTXexit0. This confirms missingstartupmetadata in the optionalcapture, not failure of the primaryRTSP relaypath.

Stagedfix recordsnativeSRTMPEGTSbytes directlyto.ts, hashesmessages, and decodesoffline; removesprematureMatroskaheaderdependency.46 realSRTsocketcopy+offlinedecode passed(actualvideo1280x720/audio48k), noGPU/inference. Stagedanalysis nowpreserves per-capture safeerrorclass/fixedmessage andprotectiontimelineevenwhenonecapturefails. Runtime stagedfixederrorclass/input/outputcodes (no rawtext). NativeSRTcaptureguard nowrequirescompletecontinuousmeasurableA/V ratherthanfileexistence.

Budget latestconductorcheckpoint43/52 with9remaining;44,45,46 use3,6left. Originalnativeattempts separatelyreported bycollector; no automaticrequeue acceptedasnewtestbudget. No changes toengine/scorer/Q. No gradingwitholdpooledscorer. Needapplyonlyaftersoak3exits; thenaffectedtests,fullgate,newAVproducersbefore20minrerunwithin52/timebox.

## 2026-10-30 05:43 UTC — original queue drained; applied capture and safe diagnostics

Readcollectorhand-backandindependentlystream-hashed all4originalsealsagainstoriginalstdoutdigests(82inventoryentries,61sourcehashesperrunmatchedbeforecopy). Originalsource/dataunchangeduntilalljobsended. CopiedQUEUE-HANDBACK. Alloriginaljobsred;4nativeexecutions+2preexecrejections;all28observedPIDsabsent,rootrunnerexitednaturally. Noactivequeuedworkremains.

AppliedlocallyprovenrawMPEGTSside-capturefixafterfreezeended; per-endpointdecodeerrors retainclass/fixedmessage/protectiontimeline. Runtime/encoder/sender nowrecordsafeclass/errno/program-definedphase anderrorcode, neverrawupstreamtext.52affectedM2suite16pass.51capture-onlyaffected16pass. Original43+4native+3localdiagnoses=50;51/52nowexecuted. Conductorgrantedceiling58,timeboxunchanged. Freshqueuewith815b420 retryfixawaitingrootcommand; onlyshortsafe-runtimepilotnext,notblind20min. Actualoldruntimecause stillunknown; engineoutputcountversusegresscountdifference indicatespresentationfailure butdoesnot identifyit. Q/independentOCR/Gate2stillpending; no privacyclaim.


## 2026-10-30 06:08 UTC — runtime diagnosis, timeout red/green, gate and A/V requalification

53: one physical120s diagnostic ended38.0375s/955frames, contended40.581%mean/61.526%max otherbusy, notforced. Safefirstobservable nativeerror senderBrokenPipeError32 network-mux, encoder same294mslater; readerEOF/SRTendprecede. No faultbefore38s (HOLD70/kill71/reconnect74), paths camera/shielded disjoint overridefalse. Logs originallyDEVNULL. Collectorhandback copied afterreading; parent19fileseal/inventory verifies againstoriginalstdoutdigestf9bc76d8...; oldbundlesunchanged.

Added bounded in-memory MediaMTX fixed-code close reader; no rawlogs.54 realRTMPpublisher four-secondgap reproducesio-timeout->BrokenPipe32 at3s config (exit1).55 identicaldriver/source green withread/write10s default (150resumedpackets,exit0). Bothserverexit0/readerstopped/credentialabsencechecks true. Commands: root scripts/host-lock exclusive env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n10 .tmp/m2/py311/bin/python .tmp/m2/repro-publisher-gap.py /tmp/agents/irl-shield/m2-relay/{54-publisher-gap-red,55-publisher-gap-green}.json, with respective stdout/stderr.log. Driver/sourceSHA inreceipts. Notproofalloldruntimefailures sharecause. Addedencodedatmonotonic/maxEgressACKwall forcadenceanalysis. Enginepilotmaxrender28.6ms/coverage12.4ms/lock46us; cannotconcludepureCPUstarvation.

56 command env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n10 .tmp/m2/py311/bin/python .tmp/m2/full-gate-56.py;96default(1Macskip)+16M2+compileall pass;56-full-gate.json/.log. Native-auth subsequent diagnosticcontract update willbecheckedbyrealmatrix. Conductorgranted62,originaltimeboxunchanged. Enqueuedboth60sAVreruns inqueue2:RTMPaab1fe0622494918a54b701bb0be78d5,SRT443f4ed3d0304e8a9aca6fd3481a2c0b. Exactargv .tmp/m2/session2-av-commands.json;sourcefrozen source-at-requalification.json. QueueUNSEALED; no20minproduceruntilAVreceiptsinspected. Oldpendingdiagnosticrootaskedwithdraw; one-shotguardpreventsphysicalrepeat. NoTwitch,scorerorenginechanges.


## 2026-10-30 06:34 UTC — A/V audits, exact DTS reproduction, final producer submission

57/58 first60sAV executions finalized. ParentreadfullAV-REQUALIFICATION-HANDBACK and independentlyverifiedbothoriginalstdoutsealanchors/all50files/exactinventories; copiedhandback. RTMPexit0functionalcomplete;SRTexit2incomplete. BothCONTENDED(memorynotokandotherbusy),notforced. Rootclosedbothpendingasclosed-one-shot; noexecutedretry. RTMPdecodedRTSP1915frames63.816s andSRT1910frames63.633s;19AVpairs each,median4.479/1.479ms,absp956.012/9.013ms. Faultkill/reconnectsurvived;203HOLDrows0metadataviolations. Encodedmaxgap.572707s/ACKmax.580188s;no>10sgapsbutstrictprotectedcadenceunqualified. NoindependentOCRgrade.

SRTsideRTSPcapturelastvideoDTS83970->83229/90000 beforeValueError.59 exactDTSsequence replaywithrealarchivevideo intoMatroska reproducesValueError22 atsamepoint; no timestampclamp. Helper .tmp/m2/repro-capture-dts.py; command env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n10 .tmp/m2/py311/bin/python .tmp/m2/repro-capture-dts.py /tmp/agents/irl-shield/m2-relay/59-capture-dts-repro.json; stdout/stderr59-capture-dts-repro.log. RawRTPpayloadnotreconstructed. ReplacementSRTsenderfailsafter8frames, originatingwhyunverified. Mainreaderdecodes(notremuxes) cameraRTSP,processedgen1/701LIVE;17mapped-indexdrops(cannotidentifyrawDTS,RTMPhas175). No mainrawpacketmanifest. All684outputsafter44sHOLDreleaseareHOLD,soSRTrecoveryNOTqualifiedforwalk. Answeredconductorfromsealeddata,nonewexecutiononmainreaderquestion.

ConductorauthorizedRTMP20min+realACLmatrixthen seal; watchesmaxonecontendedsoakretry(rootstopsbeforethird). Submittedsoak5457243dcb624b4fbffa927fad880bc2 andACL046a95aa58364472a2318e26947c457c toqueue2; SEALEDfinalset. Exactargv session2-final-commands.json; enqueue/sealreceiptsinparentreceiptdir. ACLdriverhash acl-driver-sha256.json;onecommandchecksrealRTMP/SRTpublish/authenticatedRTSPread/negativeACL/bindingsonboth127.0.0.1and100.109.49.77,validatesinheritedEX,no nestedflock. Budget59/62beforenativeexecutions,threeavailableincludingoneretry. Noobservercreated;conductorwatching. SourceFROZENunchanged. Handbackrewrittenwithcurrentpercriterionpending/partial/failedstatusesandknownlimits,nopassclaimed. Repo/private,secrets/Twitchunchanged.


## 2026-10-30 — long native failure and hypothesis checks

Conductorreportssoakfirstexecutionfailed;closedretry,ACLkeptpending. Parentreadssealedruntime/events/source:1007.492s/30001out;lastPTS1000LIVE;reconnect668s,~339secbeforefailure;gen2senderclean10033frames. Input-timestampoldlastcodeunclocked,notproofconcurrentcause. Userceiling72,originaltimeboxunchanged. Owner/conductorcheckpointd4a28a99bdda0bc44a685f31cd971babf1263781committed/pushed;parentverifiedHEADandcleansourcebeforepatch.

62tinyrealnativegen1origin600kill/gen2zero:runtimepassed12s347frames2sessionsbutprototypecleanupblockedEvent.setonkilledsender;identitymatchedownedparent/childrenSIGTERM,exits143,allgone,receipt.tmp/m2/repro62-cleanup.json.63helpercleanupfixedPASS350contiguousframes2sessions/maxgap.164s/allprocessesstopped.64codecprobeactualengineHOLDpts999.867→1002.033:libx264/NVENC66decodedframesbothPASS. Falsifiesorigin/highPTS-alonehypotheses;nooriginalbugredreproduced. Exactcommands/helperSHAinreceiptfiles62/63/64andtoolhistory;noengine/scorerpatch.

65streamtestextensionredKeyErroroperationonrealhandshakestall. Addednumericsharedworkerphaseheartbeat/countersandtimestampedinputfailures/missing-or-nonincreasingPTSobservations,novalueclamp/mappingchange.66affected4PASS,67fullLinux96default1Macskip+16M2+compileallPASS. Uncommitteddiffagainstcheckpointstream/runtime/testplusdocs,interfacescompatible. Budgetactual66beforequeuedACL(notexecutedyet),receipt61reservedso62–67filenamesarenotchronologicalslots;ceiling72. No newlongproducer. Read-onlyUltraanalysischildbelowownsnoteonly,zeroexecutions;completionwakesparent.


## Bounded recovery steering

ACL61 completed; parent verified exact original stdout seal a5fe28931a2f0abecbfaa65eb64a32adaa9db514690cf944b501f9b6a425af8b and one-file inventory. Both hosts pass all native packet/auth/binding/credential checks, uncontended15.851%mean18.975%max, forcedfalse. Runner3442769 exited empty/sealed.
68 fragmented RTMP control reproduces network-mux timeout after93ACKs; full control300ACKs. Historical attribution unproved.69 bridge experiment launched before new steer failed startup; raw receipts retained, production bridge/import removed. Conductor orders bounded egress-only recovery, cap76, deadline15UTC. Source staged only .tmp/m2/recovery, parent still legacy for red70. Test child allocated one red invocation70, parent green71/full72/fresh-soak73/retry74, reserves75/76. Current69 executed. No process retained; no further bridge work.


## Recovery green and final source freeze

Audited child70fulltest/fixture/handback/redlog/sourceSHA. Actualnative red70:fullPing300ACKs,fragment93/network-muxTimeout; saturatedLIVEbackpressure6s plusmoderatorhold producesTimeout; refusedportfailslegacycode. No fixtureerrors/survivors. Copied onlyowned2testfilesandhandback,trimmedonecosmeticEOFblank; childhandbackrelativereceiptlinks rewrittenabsolute. Shellhook falsely rejected a combinedcopy command asworktreeremoval; no worktreeoperationwasrequested/executed. Usedfile-specificpatches forreviewedownedfiles. No nativeinvocationspentbythatrejection or JSONreadprojectionerror.

Appliedboundedrecovery tostream/live/runtime. Refinedfresh-frame startup/dropbatch/currenthold handling; accepted pending-networkrecoveryframesreturnNone, onlyreadyTrue clearsinternalegressHOLD. Recoveriespersistinnewworkerstartup, no parentcritical-path eventfilewrite; archivegenerations/rootmanifestappend. 71all3regressionsPASS38.773s:fragment2connections120ACKs,backpressure2connections309ACKs,gen2allfreshHOLD/black/protected,nofailedindexreplay,moderatorholdretainedthenreleaseswithoutinternalegressholdstuck. Rate5/60exhaustsin2.358s with exactterminalcode/persistedevents. Allworkers/PIDs/listenersgone.

72fullLinux96default(1Macskip)+19M2+compilePASS. Finalone-linependingeventsdeque64cap,then73fullsamePASS(19M2in44.911s). NativeonlyCPUregressions;noindependentOCR/Qclaim. Sourcefreeze31paths fbd7909030da40858d1c83a969a2e70ccbf9491a9a8968f544569c0ac5d22aab. Follow-upsourcepatch .tmp/m2/recovery-source.patch SHA77ddc0d1edaac4de2221e5d344149299246325f9f50d3e789a973c4b3be91fc4, againstownercheckpointd4a28a9;nochildcommit/stage/push. Activecodecanonical;staged.tmp/m2/recoverycopiesSTALE.

Session3rootrunner4177108providedverifiedalive. SubmittedEXACTLYONE1200sRTMPsoak job36103e2e99f24959888f2f5d2175e282 name m2-v3-rtmp-soak andSEALED. Exactdirectliteralargv+hash+HEAD .tmp/m2/session3-soak-command.json, runtime receipt .tmp/m2/gate2-v3/m2-v3-rtmp-soak/attempt-{attempt}/runtime.json. No nestedlock;existinginheritedEXvalidator/forcedsemantics. Correctedcounter73/76beforenative;74firstsoak75onlycontendedretry76spare. Rootafter-second-contended administrativecallback prevents thirdclaim;standardqueuecodeunchanged. No newmanualnativeattempts. Rootwatching;no parentobserverornewchildwaiter. SourceFROZEN,docs-onlyuntilresult/closure.


## 2026-10-30 — session 3 attempt 2 independently audited

The notified queue attempt 2 is physical execution 1; attempt 1 was a pre-exec
readiness rejection and spent zero invocations. Native exit 0, functional
20-minute evidence complete. Budget is now 74/76; the only authorized contended
retry remains root-owned and would spend 75. No new producer, watcher, polling
loop, decode, test, or native execution was started in this audit turn.

Read-only audit verified original queue-stdout seal
2948628190006f3ab35afd350e890279b2dc473f74451d64e8c2680775a9aa90,
all 25 inventory files / 1,428,817,811 bytes / read-only modes, zero mismatches.
All 31 frozen source paths and 61 provenance hashes match current source;
provenance HEAD f9dc9482b0a46e4ad453c7da01835d92abc7e87c. Exact queue argv
matches the submitted template with attempt=2. Active implementation stayed
frozen; only the three owned documentation files changed. Audit command:
`nice -n 10 python3 .tmp/m2/audit-v3-attempt2.py`.
Audit result: `.tmp/m2/v3-attempt2-parent-audit.json`.

Recomputed frame/protection manifests agree: 36,205 contiguous encoded rows,
28,295 LIVE / 4,596 HOLD / 3,314 PROTECT, 6,496 slate. Manual-HOLD guard checks
202 rows after its explicit 250 ms grace and finds zero metadata violations;
109 accurate-stall-window rows are protected. Faults occur at 664.004 s HOLD,
665.065 s sender kill, 668.021 s reconnect, 671.001 s release. New sender exits 0
after 16,184 frames; zero egress interruptions or recoveries. There are 136
accepted input sessions / 245 disconnections under queue backpressure, and
9,329,678 discarded audio samples; do not call this lossless input/audio.

RTSP native capture has 36,115 decoded frames / 1203.820 s; SRT output capture
36,110 / 1203.633 s. Each has 822 optical/tone pairs, 105 unpaired beeps and
22 unpaired flashes. Recomputed median / absolute p95 offset: RTSP 3.271 /
4.770 ms, SRT 1.771 / 2.604 ms. Maximum decoded PTS gaps 55 / 34 ms, no
non-increasing PTS. Encoded wall max 464.551 ms, 295 gaps above two 30 fps
periods; presentation wall max 487.883 ms; max successful write/ACK 477.467 ms.
No measured wall gap exceeds 10 s. Decoded PTS continuity is distinct from
wall-clock cadence; no attribution to pure CPU starvation is supported.

The run is contended under other-busy-v2: mean 40.189%, max 73.366%, plus
memory_not_ok, forced=false, contamination valid=false. It proves RTMP
functional robustness under the exercised faults; timing/cadence qualification
is excluded. Queue bound 8/8; sampled main+MediaMTX+sender RSS peak
1,248,472 KiB, full lifecycle threads 39–85 / FDs 64–122. Steady early/late
medians are 66/67 threads and 112/114 FDs. Encoder worker, spawn helper,
GPU/VRAM remain unmeasured. All four sampled PIDs are absent; runtime cleanup
errors empty and owned sender/MediaMTX exits recorded. PID-level encoder
cleanup is not independently covered by the soak sampler.

Consolidated M2-HANDBACK.md to remove obsolete current counts, checkpoints,
deadlines and queued status. Preserved prior full text at
`.tmp/m2/M2-HANDBACK-before-v3-audit.md`; chronological red history remains here
and in child hand-backs. Updated README acceptance limits. Independent privacy
is still PENDING root corrected/all-leak OCR; Q and SRT publication remain
unqualified. All footage/derivatives benchmark-only, no music, not demo-ready.
Root was notified of exact audit and its limits. No staging/commit/push/PR or
queue mutation occurred. Root's pending retry and runner are left untouched.


## 2026-10-30 — final retry audited; M2 execution budget closed

Conductor notified attempt 5 / physical execution 2, rc 2 incomplete, then closed
all further executions at 75/76. Queue ordinals 1, 3 and 4 were pre-exec
rejections (zero budget); 2 and 5 are the only physical session-3 executions.
Job state independently read as closed-one-shot, runner metadata drained;
runner 4177108 is absent. No extra native execution, test, codec decode, OCR,
producer, polling watcher, or queue mutation occurred in this audit turn.

Read-only audit command: `nice -n 10 python3 .tmp/m2/audit-v3-attempt5.py`.
Original queue stdout seal:
53d8c9e1a5be466fc80b4f822b7d25729cd07cb52c36ac25101f58f0ca09a8c3.
All 29 files / 753,598,406 bytes / exact inventory / read-only modes verified,
zero mismatches; all 31 frozen and 61 provenance source hashes and exact argv
match. HEAD/source remain f9dc948 / fbd7909 snapshot. Result:
`.tmp/m2/v3-attempt5-parent-audit.json`. A separate read-only FLV tag inspection
was added to that audit result; it validates container tag sizes/counts/timestamps
without invoking a decoder. Final cleanup:
`.tmp/m2/v3-final-cleanup-audit.json`.

Runtime stops normally after 1208.205 s. Encoded manifest 35,944 rows vs 36,205
engine outputs: 261 skipped indices, not replayed. State totals 23,145 LIVE /
10,004 HOLD / 2,795 PROTECT, 12,799 protected rows, 11,896 slate (33.096%).
Manual-HOLD guard 202 rows after the explicit 250 ms grace, zero metadata
violations; accurate-stall protection 109 rows. This is real session survival
and writer recovery, not a second full independent-capture success.

The conductor's hypothesis that both captures stopped because of egress
reconnect is partly refuted. RTSP last packet 183.056 s, ExitError finish
185.128 s; first egress recovery 515.608 s, 330.480 s later. RTSP's earlier
interruption cause is unverified. SRT last packet 520.863 s / read-ended
520.876 s occurs during recovery. Capture source retries only initial startup;
a read failure ends the thread, so neither capture observes generation 3.
Sealed summary errors are exactly short RTSP span, too few RTSP frames and
incomplete SRT measurable A/V. RTSP prefix 5,292 decoded frames / 176.388 s,
122 pairs median/absolute-p95 4.688/8.770 ms; SRT prefix 14,868 / 495.567 s,
323 pairs 1.729/11.083 ms. No post-recovery A/V or decoded network claim.

Recovery 1: write deadline, archive-mux operation, failed index 14960, 515.608 s.
Recovery 2: generation-2 encoder-startup deadline, 521.263 s. Header-only gen2
archive 394 bytes contains no encoded media data tags. New generation 3 starts
writing at 522.174 s and ends LIVE at 1207.812 s, 20,984 manifest rows; archive
has 20,984 video data tags and 32,789 audio data tags. Manifest writes follow
encode+network-mux return, supporting successful writer/connection recovery;
independent downstream decoding after restart remains unverified. Recovery
JSONL has 3 rows but 2 unique events: first pending event was appended again
by the startup that timed out. Count unique events/runtime count, not raw lines.

Actual encoding wall gap reaches 22.525 s; presentation gap 22.511 s; max
write/reply/cleanup call 15.934 s; PTS jump 8.733 s. Thus the retry FAILS the
no-wall-gap-above-10s criterion. Algorithmic five-second timeout plus cleanup
does not prove a hard wall deadline under OS/host pressure. Both native runs
are contended: retry other-busy-v2 mean 38.411%/max 75.757% plus memory_not_ok,
forced=false, valid=false. Timing and strict cadence remain NOT QUALIFIED.

A second harness defect explains much of the extended slate: sender01-exit
records status failed, BrokenPipeError/errno32/network-mux at 515.214 s after
14,981 frames. The scheduled kill at 665.008 s finds it already exited with 2,
but Scenario._stop marks intentional_kill=true unconditionally; summarize then
exempts that failure. This is not a valid second deliberate-kill proof.
No publisher exists until sender2's first generated frame at 668.552 s:
~153.338 s outage. Generation 3 writes 4,789 HOLD/slate rows before the planned
668.006 s reconnect; longest slate run is 4,927 rows, 522.174–672.593 s.
First LIVE returns 672.613 s, 1.608 s after manual release / 4.061 s after new
sender first generation stamp. This argues against a permanently latched
egress hold; source outage and missing-ingest coverage explain the long slate.
9,324 slate rows have ingest-gap coverage (78.38%). Before recovery, 3,362
slate rows already exist. Remaining repeated input gaps/backpressure are not
all caused by egress recovery. CPU versus I/O/OS starvation is not isolated;
the observed stalled worker operation is archive-mux. Quiet/dedicated host and
real phone publisher-reconnect qualification remain operational requirements.

Input queue remains 8/8; 115 accepted sessions / 1,001 disconnections include
failed attempts during publisher absence, not 1,001 proven queue overflows.
Last input error input-backpressure; 8,029,392 audio samples dropped. Sampled
RSS peak 1,298,856 KiB, threads 29–84, FDs 56–122; encoder worker, helper and
GPU/VRAM excluded. All known retry wrapper/main/MediaMTX/sender PIDs absent;
no tested listener on 18554 TCP / 19550 TCP / 19050 UDP; no Python/MediaMTX/
FFmpeg candidate with this worktree cwd. Native worker identities were not
recorded historically, so cleanup-tree coverage remains partial. No process
retained or stopped by the audit; root runner exited naturally.

Final per-criterion hand-back updated: attempt 2 PROVES RTMP functional
robustness; retry OBSERVES real NVENC writer recovery but is incomplete; both
runs exclude timing qualification; timeout/cadence guard fails retry; memory
coverage partial; independent privacy PENDING root corrected OCR; Q and SRT
publication unqualified. No overall Gate 2 pass, leak count, dedicated-host
performance result, or public demo readiness is claimed. All frozen media
remain BENCHMARK-ONLY / no music / not demo-ready. Only three owned tracked
docs changed; implementation source remains frozen and no commit/stage/push
or PR occurred. Prior red receipts and all source versions remain intact.
