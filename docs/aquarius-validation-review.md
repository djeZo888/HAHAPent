# Aquarius autonomous validation worker review

Review date: 2026-09-09. Historical result: **PASS — offline gate for the bounded
direct-TCP plan below; superseded after the Channel F recovery failure**.
The renewed gate is recorded in the superseding repair review below.
This is an independent source and synthetic-test
review, not an actual-lamp validation result. The coordinator retains all
operational authority. The module 0.1.1 candidate remains read-only with an
empty shipped write-profile allowlist.

The reviewed files are frozen at these SHA-256 values:

| File | SHA-256 |
| --- | --- |
| `tooling/aquarius_validation.py` | `65d3ed03d8cf219f9755d3435bc36684405420b0a897c417ee3b5d5e0dc3f8d2` |
| `tests/test_aquarius_validation.py` | `d9c10366799eae3e39f837612b122cec4155bbb91885390cb0b877ee2c83c5ac` |

Changes to either file require the affected review and tests to be repeated.
The worker is an operator tool, is absent from the installed integration,
and does not enable the integration's write allowlist.

## Independent offline evidence

Run from the repository root:

```sh
.venv/bin/python -m unittest tests.test_aquarius_validation -v
.venv/bin/ruff check tooling/aquarius_validation.py tests/test_aquarius_validation.py
shasum -a 256 tooling/aquarius_validation.py tests/test_aquarius_validation.py
```

Independent result: **26 tests PASS in 8.410 seconds; Ruff PASS**. All targets
were synthetic or local loopback. No credentials, real lamp, or HA service
was used by these tests.

| Test group | Count | Evidence |
| --- | ---: | --- |
| Protocol and private configuration/report handling | 4 | Fragmented framing, bounded buffers, extended frames, independent integration wire-vector agreement, strict target/profile/channel limits, private report permissions |
| Transaction and failure simulation | 17 | Manual and Automatic recovery, exceptions after mutation, repeated stop requests, exhausted deadlines, failed verification, complete network loss, competing channel/mode changes, automatic schedule drift, preflight changes, and evidence-storage failures |
| Native TCP and detached subprocess | 5 | Fragmented replies and write echoes, ignored writes with ACKs, unambiguous zero-channel responses, query-echo rejection, and a detached child receiving SIGHUP after its first change plus SIGTERM during cleanup |

The detached-process test confirms recovery within ten seconds after both
signals; its overall result is correctly FAIL because it was interrupted.
The network-loss test correctly reports unconfirmed recovery and sends no
blind snapshot replay. Synthetic success does not establish a physical
lamp's timing or control behavior.

## Reviewed safety properties

- The worker accepts one explicit private IPv4 target on port 8080, an exact
  validation-only controller/version/six-channel profile, and one channel
  delta of one to five percentage points. It performs no discovery or
  provisioning. Shutdown and other modes are unavailable.
- Two complete, matching preflight states are required. Unknown mode,
  profile mismatch, channel drift, or an out-of-range requested result stops
  before the first control frame.
- Baseline and explicit pending intent are durably written before the
  excursion begins. Active transaction events are buffered until cleanup
  ends; a slow or failing report filesystem cannot consume the recovery
  reserve. A final reporting failure makes the overall result FAIL.
- Signal handlers set a flag. Synchronous checkpoints enter cleanup without
  asynchronously throwing through a recovery block. Further SIGINT,
  SIGTERM, or SIGHUP requests do not interrupt that cleanup.
- The experiment has a three-second absolute budget. Cleanup uses its own
  deadline at 9.5 seconds from the first intended control, preserving at
  least 6.5 seconds when the experiment uses its full budget. A command is
  refused if fewer than 1.8 seconds remain. Socket operations are bounded
  by the remaining phase budget and a 0.8-second per-operation timeout.
- A channel write is followed by Manual, a 200 ms receive quarantine, and
  an explicit queried system response on the still-open write connection.
  Only the exact emitted write echoes, ACKs, and complete extended frames
  may be discarded during quarantine. A fresh connection then independently
  reads system and all six channels. ACKs or command echoes never confirm
  output. Extra, partial, unexpected, and exact query-echo replies fail.
- Cleanup begins with a fresh guarded read. Only the baseline or the exact
  planned single-channel change permits snapshot restoration. A competing
  channel change, unknown profile/mode, Manual-to-Automatic change, or loss
  of verified Manual state stops restoration and reports FAIL.
- When needed, baseline channels are restored and independently confirmed
  in Manual, then the original mode is restored as a separate held,
  queried, and independently verified command. Automatic schedule drift
  after deliberate restoration of Automatic is allowed. Ambiguous
  Automatic state observed before confirmed recovery is preserved and
  reported FAIL, rather than treated as successful restoration.
- There are no write retries. Recovery PASS requires read confirmation
  within ten seconds; merely sending a restore command is insufficient.

The review addressed failure modes in report persistence, asynchronous
signal exceptions, competing Manual-to-Automatic changes, and incorrectly
counting ambiguous Automatic state as recovery. Each has a focused
regression in the frozen suite.

## Approved bounded execution plan

The coordinator reported ten actual HA-side native TCP **read-only** cycles
passing with stable Automatic state. Full system/channel reads took
0.322–0.520 seconds, including the 200 ms inter-query interval; connections
took 0.002–0.113 seconds with a 1.5-second probe timeout. These observations
support trying the bounded plan; they do not prove write timing or explain
the earlier short-lived SSH `nc` harness failure.

1. Run the exact reviewed worker detached in the existing HA-side runtime,
   using the protected target/profile and a new private report. Confirm
   the executable and its dependencies are already present before launch.
2. Begin with a single one-percentage-point reduction on one channel where
   the current value permits it. Preserve all other values and the original
   mode. A zero baseline instead requires a separately recorded one-point
   increase within the already authorized bound.
3. Require the worker's independent experiment and recovery confirmations,
   the reported excursion time, and a subsequent read-only state check.
   Stop on the first failure or uncertain restoration. Diagnose and confirm
   recovery before admitting any later experiment.
4. Only after that gate passes may the coordinator repeat one channel at a
   time for the remaining channels within the same maximum delta/time
   limits. Record each channel's actual evidence separately. Enabling the
   shipped write profile or claiming working HA controls requires the
   corresponding actual-lamp and native-HA evidence.

The worker cannot guarantee physical restoration after SIGKILL, host loss,
or a severed device connection. Its bounded behavior is to stop issuing
unjustified commands and report recovery as unconfirmed. This review covers
the direct-TCP worker only: a separate HA-service harness must account for
service admission, cancellation, and possible in-flight operations; an HTTP
timeout alone does not prove cancellation inside Home Assistant.

## Channel F failure and recovery repair review

Status: **PASS — superseding offline gate for the repaired bounded worker**,
2026-09-09. The historical F failure remains FAIL; this review permits its
bounded revalidation and does not convert previous failures into passes.

The original reviewed worker passed actual bounded A–E checks but failed the
Channel F recovery bound. The changed state was independently confirmed at
0.716 seconds. The first fresh recovery guard read then timed out after
0.8 seconds; the worker stopped at 1.518 seconds, abandoning the remaining
cleanup reserve. A later deliberate, freshly guarded restoration took
1.887 seconds and confirmed the original channels and Automatic mode. The
estimated total excursion was 53.16 seconds, exceeding the ten-second bound.
That estimate is not a monotonic cross-process measurement. The complete
historical outcome remains in [Task 003](../tasks/003-led-integration.md).

The earlier 26-test gate did not cover a transient recovery guard timeout
followed by a successful read within the reserved cleanup time. The repaired
worker now spends a bounded portion of the reserve on read-only attempts and
retains time for justified restoration and independent confirmation. It never
retries a write or extends the ten-second limit.

### Reviewed source and independent results

These hashes were checked before and after the independent final test run:

| File | SHA-256 |
| --- | --- |
| `tooling/aquarius_validation.py` | `1fbbb2db16a19b7b7478b699903d95bd725710d308a9c37c5114666f0ce38300` |
| `tests/test_aquarius_validation.py` | `a6849fd273cbdbca548ffde331e4af356ee7083ca06b6e916d416d5bf73d4b61` |
| `tooling/aquarius_ha_validation.py` | `4550805ee0c45a3777eb59019c4bf539e01bf75f41974e461359f7d3f3271c37` |
| `tests/test_aquarius_ha_validation.py` | `63472b0e3c0ad6ac747b94d10bdcd958ac8af26d9692a5d3a626fb3318cacf57` |

```sh
.venv/bin/python -B -m unittest tests.test_aquarius_validation tests.test_aquarius_ha_validation -q
.venv/bin/ruff check tooling/aquarius_validation.py tests/test_aquarius_validation.py tooling/aquarius_ha_validation.py tests/test_aquarius_ha_validation.py
```

Independent final result: **62 tests PASS in 53.171 seconds; Ruff PASS**.
This comprises 43 base-worker tests (28 transaction, four protocol/private-file,
11 native TCP/process) and 19 HA-adapter tests. The latter use synthetic service
implementations and a loopback HTTP server, not actual HA entity services or a
physical lamp. The actual HA framework suite separately passed **53 tests**,
including native form serialization and admitted-action cancellation coverage;
that result is also synthetic.

### Recovery behavior and scenario evidence

Each recovery read stage permits at most three fresh connections, with a shared
maximum 2.5-second read budget and a 100 ms pause between transport failures.
The deadline also subtracts a reserve from the existing 9.5-second cleanup
deadline: four seconds after the initial guard, two seconds after restored
channel confirmation when an original-mode command remains, and zero after
the final mode confirmation. Retries never reset or extend these deadlines.

Only transport failures of read-only operations may trigger another read.
Connection refusal, a clean EOF, or timeout discards that connection before
another full system/channel read. A partial frame, malformed reply, changed
profile, or competing mode is terminal. A competing mode already observed in
the system reply remains terminal even if the following channel read fails.
Full channel guards still reject unrelated changes before restoration.

The independent review also identified a lost queried-system barrier reply
during cleanup as another place where the reserve could be abandoned. The
final repair handles a transport-only failure of that query with fresh full
state reads. It does not resend the preceding channel or mode command. Expected
profile and mode must match, and exact restored channels must be confirmed
before any later original-mode command. A contradictory or partial barrier
reply remains terminal. Transport failures while sending a write or during
its receive quarantine remain terminal rather than being treated as a safely
settled command.

| Failure or scenario | Independent synthetic evidence |
| --- | --- |
| First recovery connect failure, timeout, or EOF | Fresh read-only retry succeeds, then original channels/mode confirmed within ten seconds; no duplicate writes |
| Full three-second experiment budget plus first guard failure | Recovery completes within the original deadline in both simulated-time and native TCP cases |
| Lost fresh read after channel or mode restoration | Only status reads repeat; the original five-frame command sequence is unchanged |
| Lost cleanup system barrier reply | Fresh independent state confirms the already-sent command; no command repeats |
| Lost barrier reply plus ignored channel restoration | Mismatching channels stop recovery before an Automatic command; no retry or false PASS |
| Partial/invalid/profile/competing replies | Terminal failure, no blind restoration or transport retry of unsafe state |
| Persistent network loss or exhausted retry budget | Bounded FAIL with no unguarded or late command |
| Signal interruption, report errors, slow final persistence | Earlier autonomous cleanup and evidence-boundary regressions remain passing |

Private events now include absolute monotonic timestamps and the failed
connection/query phase, without endpoint or raw error-body details. This
distinguishes future connection failures from reply timeouts and supports
same-host timing comparisons without reconstructing them from report file times.

### Renewed direct-TCP plan

The coordinator may revalidate F first with the exact repaired base-worker hash,
after a fresh read confirms the restored original mode and a stable baseline.
Use a one-point reduction where possible, or a recorded one-point increase
where the current value is zero. The earlier five successful channel results
remain historical evidence. The original ten-second limit, detached HA-side
execution, private profile/report, fresh confirmation and stop-on-first-failure
rules all remain in force. No shipped write profile is enabled by this review.
Six-channel acceptance still requires the missing actual bounded F result.

### HA-service adapter review and conditional gate

The adapter is also independently reviewed at the hashes above. It selects only
one configured Aquarius Number or the configured Manual/Automatic Select at one
explicit private HA origin. It does not follow redirects or log response bodies;
authorization arrives through stdin and remains in memory. TLS verification is
retained for HTTPS. The adapter shares the repaired base worker's guarded
finally cleanup and absolute excursion limit.

Before actual use, the coordinator must verify that the exact selected entity
registry/config entry belongs to the protected lamp target and that the installed
integration includes the reviewed three-second admitted-action deadline.
Entity-name prefixes alone cannot prove the target mapping. Actual direct-TCP
channel acceptance and the intended installed module version must also be
established before a native service test.

The installed HA 2026.9.1 API source was inspected: its blocking service call is
shielded against cancellation when the HTTP connection drops. The adapter
therefore treats HTTP completion and TCP lamp confirmation as separate evidence.
Unknown delivery remains FAIL even if a later read observes original output;
the settling interval does not prove that a delayed HA task cannot run later.
No HTTP action is retried. An uncertain Manual request prevents a second HA mode
request; any justified original-mode cleanup uses the independent TCP path.
Cleanup through HA requires at least 3.5 seconds remaining before dispatch.

The 19 adapter regressions cover Number-to-Manual and explicit Manual/Automatic
requests, independent channel/mode confirmation, competing output, signal
interruption, ignored commands, delayed service execution after an HTTP timeout,
unknown original-mode completion, read-only retries after completed HA actions,
private configuration/token handling, rejected actions, and un-followed error or
redirect responses. This is a conditional offline gate for the reviewed adapter,
not a claim that actual HA services have passed or that physical restoration is
guaranteed after persistent network or host loss.

## Release 0.2.0 source review

**PASS — independent review, 2026-09-09.** The final source enables exactly
controller bytes `(28, 30)`, version bytes `(26, 29)` and six channels, following
successful bounded direct-device confirmation of A–F and Manual/Automatic
restoration. Client and coordinator accept explicit control only from Manual
or Automatic and reject Shutdown/unknown origins; target Shutdown is rejected
before I/O. Unknown profiles remain read-only. Setup, polling, reconnect,
reload and Core startup retain query-only behavior. No recovery worker was
changed by this profile activation.

Version metadata agrees at 0.2.0. The native write-support sensor now uses its
translated name while preserving its existing unique ID. Independent source
review found no blocking issue. Local validation: **343 unit tests PASS in
104.272 seconds; 56 native HA tests PASS**. These are synthetic results;
actual native HA service acceptance is recorded separately in Task 003.
