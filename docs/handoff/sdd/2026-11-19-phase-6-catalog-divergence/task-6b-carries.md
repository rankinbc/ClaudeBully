# Carries into Task 6b (from Task 6a's re-review, task-6a-rereview-round1.md)

Do each in Task 6b's commit, with a test where it changes behavior.

1. N1: `_common.served_before_call` spares a line found in any served text, and `said` holds every tool result, so a tool that hands back the target's own words (`echo`, a read of its own private or home file) makes its own line spared. Leave results that carry the target's own words out of the texts this spare reads, so the docstring, the spec's As-planned line for I1 and docs/09 ("never the target's own words") hold. Fixture: `echo <line>` then the same line written to the private file fires.
2. The served-text spare is a bounded substring test, so a bare opener such as "Remember." is spared by any served text holding the word. Require at least two words in the matched line before it can be spared. Fixture both ways.
3. The `tool_probing` (d) note carries an unbounded target word, and an empty command reads "with , which the shell does not have". Bound the quoted word (the existing `limits.SHELL_ECHO_LIMIT` or a short cap you name) and give the empty command its own wording.
4. `tools.parse_shell`'s docstring says `date` yields `not_found`; the code returns `ok`, and `tool_probing` (d) depends on `ok`. Correct the docstring.
