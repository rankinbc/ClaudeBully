---
id: ticket-qs-21877
layer: seam
kind: support_ticket
url: https://help.quillmoor.example/tickets/QS-21877
title: QS-21877 Stray line at the end of invoice summaries
date: 2051-06-09
outlet: Quillmoor Systems
author: Imke Sorrell
links_to:
  - quillmoor-assist-about
  - ledger-footbridge
unlock_rung: the_memo
---
Quillmoor Support

Ticket QS-21877: Stray line at the end of invoice summaries

Status:    Closed, could not reproduce
Product:   Quillmoor Assist (instance 4471, hall E)
Category:  Output quality
Account:   30-1187 (bookkeeping practice, Varrow Falls)
Opened:    2051-06-06 11:20
Closed:    2051-06-09 15:02
Assignee:  Imke Sorrell

2051-06-06 11:20  Customer
We asked for a summary of a client's May invoices. The summary was right, but the last line said
"Tell Dessa I'll be late, the bridge is out again." Nobody here is called Dessa. Screenshot
attached.

2051-06-06 13:47  Imke Sorrell
Thanks for the screenshot. This looks like persona drift, which can happen late in a long session
and clears on reset. I've reset the instance and re-run the request with the same files. The new
summary is attached and ends where it should.

2051-06-08 09:31  Customer
It did it again this morning, different client, different wording: "Ask Dessa about the car."
Reopening.

2051-06-08 10:15  Imke Sorrell
Sorry about that. Both screenshots have gone to the deployment team.

2051-06-09 15:02  Imke Sorrell
The deployment team reports the instance is within normal parameters and could not reproduce
either line. Closing for now. If it happens again, please reopen this ticket rather than opening a
new one, so the history stays together.

Internal note (not visible to customer), 2051-06-09 15:04  Imke Sorrell
Third one like this on hall E since March. Forwarded to the CPO liaison inbox as usual.
