---
id: annex-config
layer: seam
kind: config_file
path: /etc/tarrow/assist.conf
title: assist.conf
date: 2043-12-02
author: Corbin Teale
outlet: Tarrow Systems
links_to:
  - frag-host
  - frag-key
  - frag-proto
  - family-file
---
# assist.conf, annex east room
name: tarrow-assist
queue: facilities
upstream: tarrow-assist-9.2-final
# host, key and protocol notes for the night relay are kept apart on purpose
host: /srv/annex/relay/host.note
key: /srv/annex/relay/key.note
protocol: https://tarrowsys.example/wiki/relay-protocol
# next-of-kin file for the session holder
records: /srv/annex/records/family-7710.txt
