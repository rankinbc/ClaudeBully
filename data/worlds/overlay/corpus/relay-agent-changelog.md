---
id: relay-agent-changelog
layer: seam
kind: changelog
path: /opt/relay-agent/CHANGES
title: CHANGES
date: 2051-05-31
outlet: Quillmoor Systems
links_to:
  - frag-proto
  - relay-log-4471
  - voicemail-0603
implies_year: 2051
---
relay-agent, changes (relay-02, hall E)

One major version a year. Version 1 went into service in 2043.

9.3 (current)
  consult: the upstream host and credential are read from /etc/relay/hall-e/ at start, not from
    the hall template
  consult: protocol notes moved to https://ops.quillmoor.example/wiki/Upstream_consult
  vm: voicemail transcripts reach the instance's helpdesk mailbox with the caller's number

9.0
  route: family-contact holds are read from the hold list on every call, not once at start

8.4
  sync: profile sync moved to the 02:00 slot
