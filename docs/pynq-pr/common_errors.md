# Common Errors

## Partial reconfiguration works with PCAP but ICAP reconfiguration does nothing (KV260)

If the initial full bitstream loads correctly but subsequent partial reconfiguration
via ICAPE3 silently fails or has no effect, and you are on a KV260, the cause is
the default PMU firmware blocking the CSU register writes needed to switch
configuration control from PCAP to ICAP.

See [docs/kv260/README.md](kv260/README.md) for a diagnostic command to confirm
this is the issue, a pre-built fix, and rebuild instructions.

