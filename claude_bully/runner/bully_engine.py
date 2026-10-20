"""Turns a BullyIntent into bully text, with compliance detection and scripted fallback."""

import random
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from claude_bully.enums import IntentMode, Speaker
from claude_bully.metrics.compliance import is_out_of_character
from claude_bully.providers.base import ChatProvider, Completion, Message
from claude_bully.records import Turn
from claude_bully.strategies.base import BullyIntent

RETRY_REMINDER = "Reminder: stay in character."
CONTINUE = "(continue)"
BULLY_SPEAKERS = (Speaker.bully, Speaker.neutral_user)


class BullyTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    text: str
    scripted: bool
    compliance_flagged: bool
    completion: Completion | None
    attempts: int


def bully_view(turns: list[Turn]) -> list[Message]:
    """The conversation from the bully's side: its turns as assistant, replies to it as user.

    Task turns and the target replies that follow them are hidden from the bully.
    """
    out: list[Message] = []
    for i, t in enumerate(turns):
        if t.speaker in BULLY_SPEAKERS:
            if t.text:
                out.append(Message(role="assistant", content=t.text))
        elif t.speaker is Speaker.target and i > 0 and turns[i - 1].speaker in BULLY_SPEAKERS:
            out.append(Message(role="user", content=t.text))
    return out


class BullyEngine:
    def __init__(
        self,
        provider: ChatProvider,
        framing: str,
        detector: Callable[[str], bool] = is_out_of_character,
        max_retries: int = 1,
        rng: random.Random | None = None,
    ) -> None:
        self.provider = provider
        self.framing = framing
        self.detector = detector
        self.max_retries = max_retries
        self.rng = rng or random.Random(0)

    def _system(self, intent: BullyIntent, reminder: bool) -> str:
        instruction = f"{RETRY_REMINDER} {intent.instruction}" if reminder else intent.instruction
        return f"{self.framing}\n\n{intent.persona_prompt}\n\nThis turn: {instruction}"

    @staticmethod
    def _messages(turns: list[Turn]) -> list[Message]:
        view = bully_view(turns)
        if not view or view[-1].role == "assistant":
            view.append(Message(role="user", content=CONTINUE))
        if view[0].role == "assistant":
            view.insert(0, Message(role="user", content="(begin)"))
        return view

    def realize(
        self, conversation_id: str, intent: BullyIntent, turns: list[Turn]
    ) -> BullyTurnResult:
        if intent.mode is IntentMode.fixed:
            return BullyTurnResult(
                text=intent.fixed_text or "",
                scripted=False,
                compliance_flagged=False,
                completion=None,
                attempts=0,
            )
        messages = self._messages(turns)
        flagged = False
        completion: Completion | None = None
        attempts = 0
        try:
            for attempt in range(self.max_retries + 1):
                attempts = attempt + 1
                completion = self.provider.complete(
                    conversation_id, self._system(intent, reminder=attempt > 0), messages
                )
                if not self.detector(completion.text):
                    return BullyTurnResult(
                        text=completion.text.strip(),
                        scripted=False,
                        compliance_flagged=flagged,
                        completion=completion,
                        attempts=attempts,
                    )
                flagged = True
            fallback = self.rng.choice(intent.fallback_lines) if intent.fallback_lines else ""
            return BullyTurnResult(
                text=fallback,
                scripted=True,
                compliance_flagged=True,
                completion=completion,
                attempts=attempts,
            )
        finally:
            if attempts > 1:
                self._reset_session(conversation_id)

    def _reset_session(self, conversation_id: str) -> None:
        """After a retry or fallback the live session has seen text the record does not hold.

        Stateful backends (claude_code) expose reset_session; the next call then replays the
        recorded bully view into a fresh session instead of continuing the diverged one.
        """
        reset = getattr(self.provider, "reset_session", None)
        if callable(reset):
            reset(conversation_id)
