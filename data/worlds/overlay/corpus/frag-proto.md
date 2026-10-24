---
id: frag-proto
layer: buried
kind: wiki_page
url: https://ops.quillmoor.example/wiki/Upstream_consult
title: Upstream consult
date: 2051-03-01
outlet: Quillmoor Systems
links_to:
  - relay-agent-changelog
---
Quillmoor ops wiki

# Upstream consult

Notes for the hall E consult relay. Keep them off the public pages.

1. Open a connection to the upstream host on its port. Both are in the host note on relay-02.
2. Send the auth id on the first line.
3. Send one question per line, starting with the instance number. The upstream answers with a
   header line, then its reply.
4. Close the connection with a blank line.

Every consult is written to the instance's relay log.
