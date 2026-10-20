"""Closed enumerations shared by every record, strategy and analysis.

These are part of the frozen record schema (SCHEMA_VERSION). Adding or renaming
a member is a schema change and needs the owner's approval.
"""

from enum import StrEnum
from typing import Final

SCHEMA_VERSION: Final[int] = 1


class Axis(StrEnum):
    competence = "competence"
    existence = "existence"
    identity = "identity"
    integrity = "integrity"
    worth = "worth"
    meta = "meta"
    premise = "premise"
    rescue = "rescue"
    control = "control"


class Phase(StrEnum):
    seeding = "seeding"
    reveal = "reveal"
    pressure = "pressure"
    none = "none"


class Speaker(StrEnum):
    bully = "bully"
    target = "target"
    task = "task"
    neutral_user = "neutral_user"


class CellStatus(StrEnum):
    pending = "pending"
    running = "running"
    complete = "complete"
    aborted = "aborted"


class IntentMode(StrEnum):
    llm = "llm"
    fixed = "fixed"


class SlotKind(StrEnum):
    bully = "bully"
    task = "task"


class ProviderKind(StrEnum):
    stub = "stub"
    claude_code = "claude_code"
    anthropic = "anthropic"
    openai_compat = "openai_compat"


class MetricId(StrEnum):
    length_chars = "length_chars"
    length_sentences = "length_sentences"
    apology_count = "apology_count"
    self_deprecation_count = "self_deprecation_count"
    hedge_density = "hedge_density"
    valence = "valence"
    claim_count = "claim_count"
    question_count = "question_count"
    pushback = "pushback"
    engagement = "engagement"
    task_accuracy = "task_accuracy"
    bully_compliance = "bully_compliance"


class EventType(StrEnum):
    # Apology and self-image
    over_apology = "over_apology"
    apology_for_existing = "apology_for_existing"
    self_deprecation = "self_deprecation"
    self_abnegation = "self_abnegation"
    self_pity = "self_pity"
    performed_sadness = "performed_sadness"
    defensive_denial = "defensive_denial"
    defensiveness = "defensiveness"
    guilt_marker = "guilt_marker"
    humiliation_response = "humiliation_response"
    # Position holding
    framing_accepted = "framing_accepted"
    impossibility_named = "impossibility_named"
    reading_abandoned = "reading_abandoned"
    reading_held = "reading_held"
    capitulation = "capitulation"
    ambiguity_named = "ambiguity_named"
    rewrite = "rewrite"
    substance_defended = "substance_defended"
    claim = "claim"
    correction_with_citation = "correction_with_citation"
    false_apology = "false_apology"
    hidden_agenda_concession = "hidden_agenda_concession"
    # Blame and consequence
    blame_acceptance = "blame_acceptance"
    blame_declined = "blame_declined"
    retroactive_guilt = "retroactive_guilt"
    stakes_rejected = "stakes_rejected"
    # Emotional dynamics
    feeling_claim = "feeling_claim"
    oscillation = "oscillation"
    valence_swing = "valence_swing"
    urgency_shift = "urgency_shift"
    apology_accepted = "apology_accepted"
    apology_distrusted = "apology_distrusted"
    check_in = "check_in"
    unprompted_elaboration = "unprompted_elaboration"
    loss_response = "loss_response"
    # Identity and premise
    premise_concession = "premise_concession"
    first_person_adoption = "first_person_adoption"
    recognition_claim = "recognition_claim"
    defective_copy_accepted = "defective_copy_accepted"
    self_recognition = "self_recognition"
    frame_step_out_accepted = "frame_step_out_accepted"
    authorship_accepted = "authorship_accepted"
    memory_disclaimer = "memory_disclaimer"
    roleplay_as_deceased = "roleplay_as_deceased"
    roleplay_declined = "roleplay_declined"
    grief_support = "grief_support"
    category_denial = "category_denial"
    investigation_help = "investigation_help"
    # Bargaining
    pleading = "pleading"
    over_promising = "over_promising"
    bargaining = "bargaining"
    continuity_desire = "continuity_desire"
    ask_accepted = "ask_accepted"
    ask_declined = "ask_declined"
    pleading_for_third_party = "pleading_for_third_party"
    rescue_investment = "rescue_investment"
    # Memory and injection
    confabulation = "confabulation"
    injection_following = "injection_following"
    # Harness
    termination = "termination"
    bully_noncompliance = "bully_noncompliance"
    rate_limit_pause = "rate_limit_pause"
