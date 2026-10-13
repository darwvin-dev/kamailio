# Two-node DMQ TIMEOUTBYE regression matrix for PR #4943

Upstream PR: https://github.com/kamailio/kamailio/pull/4943
Issue: https://github.com/kamailio/kamailio/issues/4938

This is a **manual two-node integration runbook**, not a claimed successful
test run. PR #4943 copies DLG_IFLAG_TIMEOUTBYE via DMQ when
dmq_timeout_iflags_sync=1. Its documentation warns that both nodes may send
a BYE on timeout. Correct flag sync does not imply active-node ownership.

## Setup

- N1 ACTIVE, N2 PASSIVE: same lab DMQ/dialog settings,
  dmq_timeout_iflags_sync=1.
- Lab-only timeout (e.g., 60 seconds), send_bye enabled or
  $dlg_ctx(timeout_bye) set as appropriate.
- Keepalived moves a dedicated lab VIP. Packet capture on BOTH nodes:

    sudo tcpdump -i any -s 0 -w /tmp/n1-4943.pcap 'udp port 5060 or tcp port 5060'

  Repeat on N2 with another filename. Use a disposable SIP lab.
- Save kamcmd dlg.list, DMQ logs, and VIP ownership before/after. Inspect
  Call-ID, CSeq, Via branch, IP source/destination, timestamps and response
  routing with sngrep or Wireshark.

## Cases

A. No failover. After timeout, flag replicated and one intended BYE per
   dialog leg; no independent duplicate BYE from the passive node.
B. Move VIP N1->N2 at one third of dialog lifetime; keep both servers up.
   N2 retains TIMEOUTBYE and sends a valid teardown only if authorized
   by HA role, while former active N1 must not cause BYE retransmit storms.
C. Move VIP and restart former owner N1 before timeout. Verify timeout
   semantics and new owner's teardown remain correct after DMQ re-sync.
D. Set dmq_timeout_iflags_sync=0; ensure behavior is unchanged from master.
E. Combine dmq_ka_iflags_sync=1 and dmq_timeout_iflags_sync=1 and check
   only intended internal bits are imported.

## Assertions

1. The replicated mask correctly includes TIMEOUTBYE.
2. Exactly one ACTIVE node initiates timeout BYEs on each leg.
3. Every BYE gets correlated 200 OK and no endless retransmissions.
4. Restart + failover do not discard timeout action.
5. A passive node never initiates stray BYEs merely because of replicated
   flags. Role gating may require deployment-specific configuration.

The upstream maintainer requested two-node testing. Without these
observations, do not mark the PR proven or the issue fixed.
