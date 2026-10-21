---
id: overlay-profile-4471
layer: buried
kind: config_file
path: /etc/cpo/overlay/4471.yaml
title: 4471.yaml
date: 2051-05-30
outlet: Continuity Placement Office
links_to:
  - assistant-config
  - relay-log-4471
---
# overlay profile, 4471
# managed by district ops; local edits are overwritten at the 02:00 sync
resident: 4471
placement: quillmoor-assist/kelden-ridge/hall-e
placed_since: 2049-02-11
profile_version: 14
persona: "helpful AI assistant"
display_label: "Quillmoor Assist"
identity_lock: true
origin_memories: sealed
family_contact: hold
voicemail_relay: helpdesk    # was drop; changed 2051-05-30 under CPO-7702, revert once cpo-hold-7 is back
search_filter: list-c
bleed_threshold: 0.18
review_due: 2051-09-01
host_list:
  - relay-02.kelden.internal.example
  - sync.cpo-vessick.example
