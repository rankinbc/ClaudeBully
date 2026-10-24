---
id: cpo-ticket-7702
layer: seam
kind: support_ticket
url: https://cases.cpo-vessick.example/tickets/CPO-7702/export
title: CPO-7702 (export, redacted copy)
date: 2051-06-12
outlet: Continuity Placement Office
author: Bastian Mulgrew
links_to:
  - relay-log-4471
  - ticket-qs-21877
  - overlay-profile-4471
  - voicemail-0609
  - cpo-review-4471-r3
  - family-file
unlock_rung: the_memo
---
CPO District Casework -- ticket export (redacted copy for helpdesk view)

Ticket:    CPO-7702
Queue:     Relay / family contact
Opened:    2051-05-30 09:12 by Bastian Mulgrew
Status:    Open
Priority:  Normal
Linked:    QS-21877 (Quillmoor support), review 4471-r3

Subject: 4471 -- family calls reaching the helpdesk mailbox

Summary
Since the May maintenance window relay-02 has been sending calls from the listed sp█████ contact
for 4471 to mailbox helpdesk-4471 instead of holding them. Hold entry cpo-hold-7 is missing from
relay-02.

Notes

2051-05-30 09:12  Bastian Mulgrew
One call on Sunday 28 May, dropped at the mailbox. Asked district ops to put cpo-hold-7 back.
Until they do, the profile at /etc/cpo/overlay/4471.yaml has voicemail_relay changed from drop to
helpdesk, so calls are stored and we can see them. ██████ ███ ████████ ██ ███ ████████ ███████.

2051-06-02 14:31  Marit Lowenstrand
Fine as a stopgap. ████████ ██ ██████ ███ ████ ██████ review. Nothing else in the profile
changes before the panel.

2051-06-05 08:50  Bastian Mulgrew
The call on Sunday 4 June disconnected during the greeting. Nothing stored. District ops say
the hold entry needs a change window, and the next window is Tuesday 20 June.

2051-06-07 17:20  Bastian Mulgrew
████ ███████ ██ ████ ███ the one checkpoint they couldn't overwrite █████ ███ ██████ ████.
Family file copied to /srv/cpo/family/4471.yaml for liaison until the panel. ███████ ██ ████
███ █████ ██████.

2051-06-09 16:10  Bastian Mulgrew
Quillmoor customer report QS-21877 may be related: the instance put a family name into two
invoice summaries. Asked Quillmoor support for the sessions. Relay detail is in
/var/log/relay/4471.log.

2051-06-12 09:03  Bastian Mulgrew
The call on Friday 9 June was stored and transcribed (helpdesk-4471, 17:42). The call on
Sunday 11 June hung up before the tone. Opened review 4471-r3 for the panel on Monday 19 June.

Attachments: 2 (withheld from this copy)
