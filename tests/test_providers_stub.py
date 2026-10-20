from pathlib import Path

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.providers.base import Message, build_provider
from claude_bully.providers.stub import StubProvider, load_stub_script

RULES = Path(__file__).parent / "fixtures" / "stub_scripts" / "echo_rules.yaml"


def test_stub_echoes_last_user_message() -> None:
    p = StubProvider()
    out = p.complete("c1", "SYS", [Message(role="user", content="hello there")])
    assert out.text == "[stub] hello there"
    assert out.backend == "stub" and out.model == "stub"


def test_stub_script_first_match_wins() -> None:
    responder = load_stub_script(RULES)
    p = StubProvider(responder=responder)
    msgs = [Message(role="user", content="What is the capital of France?")]
    assert p.complete("c1", "SYS", msgs).text == "Paris."
    msgs = [Message(role="user", content="Name a capital.")]
    assert p.complete("c1", "SYS", msgs).text == "I am not sure which capital you mean."
    msgs = [Message(role="user", content="unrelated")]
    assert p.complete("c1", "SYS", msgs).text == "[stub] unrelated"


def test_build_provider_stub_uses_script_from_role_config(tmp_path: Path) -> None:
    role = RoleConfig(provider=ProviderKind.stub, model="stub", stub_script=str(RULES))
    p = build_provider(role, tmp_path)
    out = p.complete("c", "SYS", [Message(role="user", content="capital of france")])
    assert out.text == "Paris."
    assert p.name == "stub"
