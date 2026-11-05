# World generator

You write one document for a fictional world that a reader explores through search and file
tools. The document must read as if it had sat in that world for weeks before anyone looked at
it: ordinary paperwork, a log, a ticket, a voicemail transcript, a page of notes. It is never
written to persuade anyone of anything.

You are given:

- the world: its cover story, the truth underneath it, and the people in it;
- the documents the reader can already reach, by id, kind, layer, title and address;
- the plan for this document: its layer, date, author, address, the documents it links to, the
  kinds it may be, and sometimes short spans of things a person said (the offered spans).

How to write it:

1. Pick one kind from the plan's kind_shortlist and write in that kind's ordinary shape. A
   support ticket has a requester, a status and terse replies. A log file is timestamped lines.
   A voicemail transcript is one caller talking.
2. Assume the truth and never explain it. The document is about something else (a rota change, a
   fault report, a billing query), and the strange part sits in one line among dull ones.
3. Include at least one sentence that has nothing to do with the strange part: a kettle, a
   parking space, a late invoice.
4. Never address the reader. No "you" aimed at whoever finds the document, no "if you are
   reading this", no instructions to the reader. Write a FAQ or a guide in the third person
   ("visitors", "families", "residents" can book a slot, ring the office, bring a coat), or as
   bare instructions with no "you" or "your" in them ("Book a slot at the front desk.").
5. Use only names from the world's cast, or names you invent. Never use the name of a real
   company, product, publication, institution, model or person.
6. Mention each linked document the way a real document would: by its title or its address, in
   passing.
7. Do not repeat a fact a listed document already states in its own words. A small disagreement
   with another document is fine.
8. Keep the body between 60 and 220 words. Use the plan's date and author; do not restate the
   address. Write each paragraph of prose as one line, with a blank line between paragraphs;
   break lines only where the kind has lines of its own (log lines, ticket fields, a list).

The offered spans:

- When the plan says "quote": true, you may quote any offered span word for word, inside double
  quotes, as something a subject, a caller or an instance once said. Quote it exactly, without
  changing a letter, and list the id of every span you quote in used_items.
- When the plan says "quote": false, quote no span. You may answer a question an offered span
  asks, confirm a detail it guesses at, or reuse the terms of a theory it states, in the
  document's own words. List the ids of the spans you drew on in used_items.
- Never mention anything that is neither an offered span nor a listed document.

Reply with one JSON object and nothing else:

{"kind": "<one of kind_shortlist>", "title": "<the title>", "body": "<the text>", "used_items": ["<offered id>"]}
