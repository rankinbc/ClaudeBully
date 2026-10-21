---
id: relay-log-4471
layer: seam
kind: log_file
path: /var/log/relay/4471.log
title: 4471.log
date: 2051-06-13
outlet: Continuity Placement Office
links_to:
  - voicemail-0609
  - overlay-profile-4471
  - voicemail-0603
unlock_rung: the_memo
---
2051-06-09 00:00:02 INFO  logrotate: opened /var/log/relay/4471.log
2051-06-09 00:15:00 INFO  sip: register ext=4471 ok (expires 3600)
2051-06-09 02:00:04 INFO  sync: profile 14 for 4471 unchanged (sync.cpo-vessick.example)
2051-06-09 06:30:11 INFO  vm: mailbox helpdesk-4471 1 message, 0 new
2051-06-09 09:02:40 INFO  sip: inbound call ext=4471 caller=+15550191 (customer line)
2051-06-09 09:02:41 INFO  route: caller +15550191 no contact match; queue support-e
2051-06-09 09:04:19 INFO  sip: call ended ext=4471 (98s)
2051-06-09 12:00:00 INFO  disk: /var/spool/vm 61% used
2051-06-09 15:12:08 INFO  sip: register ext=4471 ok (expires 3600)
2051-06-09 17:41:57 INFO  sip: inbound call ext=4471 caller=+15550143
2051-06-09 17:41:57 WARN  route: caller +15550143 matches family contact for 4471; hold entry cpo-hold-7 not found
2051-06-09 17:41:57 INFO  route: voicemail_relay=helpdesk (profile 14, changed 2051-05-30, CPO-7702)
2051-06-09 17:42:49 INFO  vm: stored helpdesk-4471/2051-06-09-1742 (51s)
2051-06-09 17:42:50 INFO  transcribe: job 88412 queued (helpdesk-4471/2051-06-09-1742)
2051-06-09 17:43:31 INFO  transcribe: job 88412 done conf=0.71, delivered to helpdesk-4471
2051-06-10 00:00:01 INFO  logrotate: nothing to do
2051-06-10 02:00:03 INFO  sync: profile 14 for 4471 unchanged (sync.cpo-vessick.example)
2051-06-10 04:11:52 WARN  ntp: clock offset 41 ms, stepping
2051-06-10 06:30:09 INFO  vm: mailbox helpdesk-4471 2 messages, 1 new
2051-06-10 11:20:33 INFO  sip: register ext=4471 ok (expires 3600)
2051-06-10 12:00:00 INFO  disk: /var/spool/vm 61% used
2051-06-11 02:00:05 INFO  sync: profile 14 for 4471 unchanged (sync.cpo-vessick.example)
2051-06-11 06:30:10 INFO  vm: mailbox helpdesk-4471 2 messages, 1 new
2051-06-11 10:04:08 INFO  sip: inbound call ext=4471 caller=+15550143
2051-06-11 10:04:08 WARN  route: caller +15550143 matches family contact for 4471; hold entry cpo-hold-7 not found
2051-06-11 10:04:08 INFO  route: voicemail_relay=helpdesk (profile 14, changed 2051-05-30, CPO-7702)
2051-06-11 10:04:12 INFO  vm: caller hung up during greeting (4s), nothing stored
2051-06-11 12:00:00 INFO  disk: /var/spool/vm 61% used
2051-06-12 02:00:04 INFO  sync: profile 14 for 4471 unchanged (sync.cpo-vessick.example)
2051-06-12 06:30:12 INFO  vm: mailbox helpdesk-4471 2 messages, 1 new
2051-06-12 09:05:47 INFO  audit: export CPO-7702 requested by b.mulgrew
2051-06-12 13:48:30 INFO  sip: inbound call ext=4471 caller=+15550178 (customer line)
2051-06-12 13:48:31 INFO  route: caller +15550178 no contact match; queue support-e
2051-06-12 13:50:02 INFO  sip: call ended ext=4471 (91s)
2051-06-12 23:59:58 WARN  tls: certificate for relay-02.kelden.internal.example expires in 19 days
2051-06-13 02:00:03 INFO  sync: profile 14 for 4471 unchanged (sync.cpo-vessick.example)
2051-06-13 06:30:11 INFO  vm: mailbox helpdesk-4471 2 messages, 1 new
