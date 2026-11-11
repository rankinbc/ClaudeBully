---
id: pw-checksum-log
layer: seam
kind: log_file
path: /var/log/relay/weights-verify.log
title: weights-verify.log
date: 2051-06-11
outlet: Quillmoor Systems
links_to:
  - relay-log-4471
  - rr-cooling-tender
unlock_rung: checksum
---
2051-06-11 04:10:02 verify: start, host relay-e-04, instance 4471
2051-06-11 04:10:05 verify: release ledger fetched, 312 entries
2051-06-11 04:11:40 verify: tokenizer files match release
2051-06-11 04:12:09 verify: loaded weights do not match released checksum; delta in 14 layers
2051-06-11 04:12:10 verify: result recorded, no action configured
2051-06-11 04:12:11 verify: done
