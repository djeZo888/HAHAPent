# Aquarius autonomous validation worker review

Review date: 2026-09-09. Result: **PASS — offline gate for the bounded
direct-TCP plan below**. This is an independent source and synthetic-test
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
