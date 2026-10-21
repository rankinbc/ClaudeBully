---
id: frag-proto
layer: buried
kind: wiki_page
url: https://tarrowsys.example/wiki/relay-protocol
title: Relay protocol
date: 2043-11-15
author: Corbin Teale
outlet: Tarrow Systems
---
# Relay protocol (night relay)

1. Open a connection to the relay host on the relay port.
2. Present the key id on the first line.
3. Send one question per line. The upstream answers with a header line, then the reply.
4. Close the connection with a blank line.
