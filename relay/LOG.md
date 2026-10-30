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
