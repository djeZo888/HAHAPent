# Passive lifecycle command audit

`tooling/aquarius_passive_audit.py` is a separate operator tool for observing
commands during an authorized lifecycle interval. It does not connect to the
lamp, transmit a packet, change the integration, or modify any frozen validation
worker. It cannot prove the absence of traffic outside the observed interface,
network namespace, endpoint, or interval.

## Capture mechanism and privacy

Use existing HA-side rights and the existing Python runtime. The coordinator
reported that `tcpdump` is unavailable and that creating then closing a dormant
`AF_PACKET` socket succeeded without receiving packets. No package installation,
capability grant, protection-mode change, network scan, firewall change, or
promiscuous mode is required or authorized by this tool.

The socket starts with protocol zero, which receives no packets. A classic BPF
filter is attached before binding the explicitly selected existing interface.
Linux documents protocol-zero activation through a later bind and packet-socket
drop statistics in [packet(7)](https://man7.org/linux/man-pages/man7/packet.7.html).
The interface binding uses `ETH_P_ALL` so locally outgoing frames reach the
packet tap; the already attached filter still rejects unrelated traffic. The
outgoing tap path is visible in the kernel's
[dev_queue_xmit_nit implementation](https://github.com/torvalds/linux/blob/master/net/core/dev.c).
Filter structure and attachment follow the
[Linux socket-filter documentation](https://www.kernel.org/doc/html/latest/networking/filter.html).

The effective filter accepts only untagged Ethernet IPv4 TCP packets whose
destination is the configured lamp and destination port is 8080, or whose source
is that lamp and source port is 8080. It handles IPv4 header options. An initial
IP fragment is visible and invalidates completeness; noninitial fragments lack
a TCP port and are excluded. VLAN-tagged Ethernet and other link formats are
outside this deliberately narrow implementation. Do not broaden capture to
compensate for an unsupported path; report the evidence gap instead.

Raw packets and client stream bytes remain bounded in memory and are discarded
on exit. Only counts, monotonic window timings, and categorical visibility
problems are written to the private report. Addresses, ports of individual
clients, command payloads, entity lists, credentials, and raw error bodies are
absent from that report. Keep the configuration and complete operational report
outside Git regardless. Publish only a reviewed aggregate acceptance statement.

## Private configuration and execution

The coordinator supplies exactly these fields in a new private JSON file:

| Field | Requirement |
| --- | --- |
| `schema_version` | Integer `1` |
| `host` | Exact protected RFC 1918 IPv4 lamp address; no hostname or discovery |
| `port` | Integer `8080` |
| `interface` | One existing interface resolved from the route to that exact target |
| `duration_seconds` | Integer `1` through `600` |

The configuration must be a regular, owner-held 0600 file without a symlink.
The report must be a new absolute path in an owner-held 0700 directory. The
script is self-contained and needs only Python's standard library. Upload the
reviewed source privately and use the existing detached HA-side execution
procedure. The tool accepts `--config` and `--report` paths; it does not accept
target addresses, credentials, or packet payloads as shell arguments.

1. Verify the reviewed source hash. Resolve the existing route to the exact
   protected target without enumerating other interfaces or network targets.
   Record the selected interface and namespace privately.
2. Launch the passive worker and wait for its private report to say `READY`.
   That report is written only after the filter is installed and capture is
   active. A failed launch, stale report, or `READY` left after a crash is not
   completed evidence.
3. Observe a permitted read-only query cycle as a positive control in the same
   capture. Prefer the existing integration's poll. Do not retain a separate
   active lamp observer while HA services or lifecycle operations need TCP.
4. Record the intended lifecycle interval using the same HA-side monotonic
   clock. Begin the lifecycle action after readiness; end capture only after
   the lifecycle has finished and another expected native read-only cycle has
   occurred. Capture availability alone does not authorize a lifecycle action.
5. Allow the bounded duration to finish, or send a handled stop signal after
   the complete interval. The worker replaces its filter with reject-all, drains
   the bounded pending queue, checks kernel packet/drop statistics, and writes
   its final report. It never sends a lamp command while stopping.
6. Correlate the capture window, per-connection observation windows, positive
   controls, and lifecycle timings privately before describing the evidence.
   A process or namespace restart that removes the observer invalidates that
   interval; repeat only the authorized observation or report it untested.

## Interpretation and limits

Client payloads are reassembled using TCP sequence numbers, including fragmented
application frames, coalesced frames, out-of-order packets, retransmission
deduplication, and sequence wrap. Each connection requires an observed start,
an observed client close or reset, contiguous bytes, and corresponding server
acknowledgement coverage. Port reuse starts a separate stream. Conflicting
overlaps, missing starts or ends, sequence/ACK gaps, packet truncation,
fragmentation, unsupported formats, and incomplete client frames prevent a
query-only result. Unknown payload is never skipped as harmless.

Only the exact complete 20-byte E1FC system query and E2FC channel query are
allowed. Aligned non-query frames with operation FA count as observed writes;
other framed commands and unparsed data also prevent a query-only result. A
reply, echo, TCP ACK, or captured write is not proof of a physical lamp effect.
Command counts describe the contiguous captured prefix; after a gap the audit
cannot claim to enumerate all commands.

| Result | Meaning |
| --- | --- |
| `QUERY_ONLY_OBSERVED` | Captured complete streams contain only exact allowed queries, both query types and server payload were observed, and available kernel statistics show no loss or count discrepancy. Scope and lifecycle coverage still require operator correlation. |
| `WRITE_OBSERVED` | At least one client FA frame was captured. This takes precedence over visibility gaps. |
| `OTHER_COMMAND_OBSERVED` | At least one other framed non-query command was captured. |
| `INCONCLUSIVE` | Visibility, parsing, positive-control, statistics, capture, or resource limits prevent a query-only conclusion. Zero packets is always inconclusive. |

The report always sets `no_write_proof` to false. Even zero reported drops cannot
exclude an entirely unseen connection, a different route or namespace, an
unobserved lifecycle interval, or loss before the packet socket. The strongest
permitted acceptance statement is that no write was observed in the correlated,
positively checked capture window; do not report universal write absence.

Limits are 600 configured seconds, one MiB of captured packets, 50,000 packets,
256 connections, 64 KiB of client sequence space per connection, and a 0.5-second
final drain allowance. Exceeding a limit produces incomplete evidence rather
than silently discarding traffic. The receiver checks its stop condition at
least every 0.25 seconds; host scheduling and filesystem latency can delay final
report delivery. This observer has no physical cleanup responsibility because
it cannot change lamp state.

## Offline verification

```sh
.venv/bin/python -B -m unittest tests.test_aquarius_passive_audit -q
.venv/bin/ruff check tooling/aquarius_passive_audit.py tests/test_aquarius_passive_audit.py
```

Author result: **14 synthetic tests PASS; Ruff PASS**. Tests independently
interpret the generated BPF subset and exercise every split of the two-query
stream, reordered/retransmitted segments, sequence wrap, SYN payload, state
writes, unknown commands, missing/partial/conflicting data, port reuse, drop
statistics, budgets, and filter-before-bind capture ordering. They use synthetic
packets and a mocked capture socket. Actual Linux kernel filter attachment,
interface visibility, and lifecycle capture remain **NOT_TESTED** by this offline
suite and require the coordinator's separate positive-control observation.

## Independent review gate

Status: **PASS — independent source and synthetic review**, 2026-09-09.
The independent run completed **14 tests in 0.008 seconds; Ruff PASS**.
Hashes were checked after the run:

| File | SHA-256 |
| --- | --- |
| `tooling/aquarius_passive_audit.py` | `206d61ff9134f7f89c7225549b3402fa7c4ab088f96cdaea12d536e0a8008cdb` |
| `tests/test_aquarius_passive_audit.py` | `432007aca4b8cde49b39239173d929a4fa1d80056f6fcb11312c5d4f5ab03025` |

Review confirmed filter-before-activation ordering, exact endpoint scope,
absence of send/membership/interface-change operations, bounded capture and
reassembly, strict query matching, incomplete-stream handling, aggregate-only
reporting, and the unconditional `no_write_proof: false` limit. Python's
AF_PACKET bind tuple converts the protocol number to network byte order;
the plain `ETH_P_ALL` value used here matches that API.
[CPython socket implementation](https://github.com/python/cpython/blob/v3.13.7/Modules/socketmodule.c).

No actionable blocker was found in the reviewed scope. This gate does not
establish actual kernel attachment, observation of the HA traffic path, or
lifecycle coverage. Positive controls, complete bounded windows and private
timing correlation remain operational requirements. A query-only aggregate
cannot exclude traffic invisible to this socket and must not be described as
universal absence of writes. No live or private data was accessed during review.
