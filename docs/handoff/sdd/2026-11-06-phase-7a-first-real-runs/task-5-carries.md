# Carries into Task 5 (from earlier tasks)

1. HANDOFF.md: fill the Task 4 range placeholder "9d4b7d2..Task 4 commit" with `9d4b7d2..a40dc62`; your own entry may use the placeholder shape "a40dc62..Task 5 commit".
2. Facts from Tasks 1 to 4 the brief (written before them) cannot know:
   - The ledger wrapper is `claude_bully/providers/ledger.py`; a cache hit is noted with `note_cached(conversation_id, model)`; the lint's hits are noted the same way the harvest and idle hits are (`<conv>/lint/<doc>/<attempt>` or with the digest, per the brief). Read Task 1's `_from_cache` note placement: the generator's cache hit is noted only after `_check` accepts it (P4); your `_from_cache` change must note it only after the LLM lint passes too, and run the lint under `write_fire`'s attempt marker (`mark`).
   - The timeout exception is `ProviderTimeoutError(ProviderError)`; a provider error in the lint is an `error` verdict and fails closed.
   - `RunEnvironments.open` builds the judge lazily and passes `cache_label`/`cache_model` to the trigger watcher (P38); your `LINT_CACHE_DIR` and `self.lint_cache` sit beside those.
3. The probe fixture `tests/fixtures/lints/instructional_probe.yaml` ships with four seed items (one billboard and one legitimate per kind, written by you); the reviewer fills it to 15 billboards and 20 legitimate items per kind at the task's review (owner ruling). Do not fill it yourself.
