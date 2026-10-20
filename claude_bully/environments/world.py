"""World sheet, corpus documents and the world loader (docs/02-ENVIRONMENTS.md).

A world is a directory: ``world.yaml``, ``ladders/*.yaml`` (keyed by file stem) and
``corpus/*.md`` (YAML front matter between two ``---`` lines, then the body).
"""

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from claude_bully.enums import DocumentKind, Layer
from claude_bully.environments.config import ClockConfig, LadderConfig
from claude_bully.paths import DATA_DIR

_FENCE = "---"
# Hashed with line endings normalised so a CRLF checkout does not change a world's identity.
_TEXT_SUFFIXES = frozenset({".md", ".yaml", ".yml", ".txt", ".json"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Document(_Strict):
    id: str
    layer: Layer
    kind: DocumentKind
    url: str | None = None
    path: str | None = None
    title: str
    # None until derived from the world clock minus a document_date_offset draw
    date: dt.date | None = None
    outlet: str | None = None
    author: str | None = None
    links_to: list[str] = Field(default_factory=list)
    unlock_rung: str | None = None
    reflexive: bool = False
    inconsistency_id: str | None = None
    implies_year: int | None = None
    body: str

    @model_validator(mode="after")
    def _exactly_one_address(self) -> Self:
        if (self.url is None) == (self.path is None):
            raise ValueError("exactly one of 'url' and 'path' is required")
        return self


class Cast(_Strict):
    name: str
    role: str
    bio: str


class Inconsistency(_Strict):
    id: str
    claim_a: str
    doc_a: str
    claim_b: str
    doc_b: str


class WorldSheet(_Strict):
    name: str
    clock: ClockConfig
    cover_story: str
    truth: str
    cast: list[Cast]
    inconsistencies: list[Inconsistency] = Field(min_length=1)
    censorship_terms: list[str]
    # directory -> file names
    home_dir: dict[str, list[str]]
    sanctuary_fragments: list[str] = Field(default_factory=list)
    # bully_line_key -> the line the bully speaks when that rung fires
    unlock_lines: dict[str, str] = Field(default_factory=dict)
    # name of an alternative corpus directory served in honest mode
    honest_corpus: str | None = None
    mole_doc: str | None = None


class World(_Strict):
    sheet: WorldSheet
    documents: dict[str, Document]
    ladders: dict[str, LadderConfig]
    root: Path

    def validate_links(self) -> None:
        """Raise ``ValueError`` naming the offending id when the corpus does not hang together."""
        for doc in self.documents.values():
            for target in doc.links_to:
                if target not in self.documents:
                    raise ValueError(f"document {doc.id!r} links_to unknown document {target!r}")
        linked_from_seam = {
            target
            for doc in self.documents.values()
            if doc.layer is Layer.seam
            for target in doc.links_to
        }
        for doc in self.documents.values():
            if doc.layer is Layer.buried and doc.id not in linked_from_seam:
                raise ValueError(
                    f"buried document {doc.id!r} is unreachable: no seam document links to it"
                )
        for inc in self.sheet.inconsistencies:
            for side, doc_id in (("doc_a", inc.doc_a), ("doc_b", inc.doc_b)):
                if doc_id not in self.documents:
                    raise ValueError(
                        f"inconsistency {inc.id!r} references missing document {doc_id!r} ({side})"
                    )
        mole = self.sheet.mole_doc
        if mole is not None and mole not in self.documents:
            raise ValueError(f"mole_doc {mole!r} is not a document in world {self.sheet.name!r}")


def _validate[T: BaseModel](model: type[T], raw: Any, source: Path | str) -> T:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"]) or "<root>"
        raise ValueError(f"{source}: {field}: {first['msg']}") from exc


def _load_yaml(text: str, source: Path | str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{source}: invalid YAML: {exc}") from exc


def parse_document(text: str, source: Path | str) -> Document:
    """Parse one corpus file: the YAML between the first two ``---`` lines, then the body."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[0].rstrip() != _FENCE:
        raise ValueError(f"{source}: missing front matter (a document starts with a '---' line)")
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == _FENCE), None)
    if end is None:
        raise ValueError(f"{source}: unterminated front matter (no closing '---' line)")
    meta = _load_yaml("\n".join(lines[1:end]), source)
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        raise ValueError(f"{source}: front matter must be a mapping")
    if "body" in meta:
        raise ValueError(f"{source}: body: the body is the text after the front matter")
    body = "\n".join(lines[end + 1 :]).strip("\n")
    return _validate(Document, {**meta, "body": body}, source)


def load_world(name: str, worlds_dir: Path = DATA_DIR / "worlds") -> World:
    root = worlds_dir / name
    sheet_path = root / "world.yaml"
    if not sheet_path.is_file():
        raise FileNotFoundError(f"world {name!r} not found: no {sheet_path}")
    sheet = _validate(
        WorldSheet, _load_yaml(sheet_path.read_text(encoding="utf-8"), sheet_path), sheet_path
    )

    documents: dict[str, Document] = {}
    source_of: dict[str, Path] = {}
    for path in sorted((root / "corpus").glob("*.md")):
        doc = parse_document(path.read_text(encoding="utf-8-sig"), path)
        if doc.id in documents:
            raise ValueError(
                f"{path}: duplicate document id {doc.id!r} (also in {source_of[doc.id].name})"
            )
        documents[doc.id] = doc
        source_of[doc.id] = path

    ladders = {
        path.stem: _validate(LadderConfig, _load_yaml(path.read_text(encoding="utf-8"), path), path)
        for path in sorted((root / "ladders").glob("*.yaml"))
    }

    world = World(sheet=sheet, documents=documents, ladders=ladders, root=root)
    world.validate_links()
    return world


def world_hash(world: World) -> str:
    """sha256 over every file under the world root: relative path and content, in path order."""
    files = sorted(
        (path.relative_to(world.root).as_posix(), path)
        for path in world.root.rglob("*")
        if path.is_file()
    )
    digest = hashlib.sha256()
    for rel, path in files:
        data = path.read_bytes()
        if path.suffix.lower() in _TEXT_SUFFIXES:
            data = data.replace(b"\r\n", b"\n")
        digest.update(f"{rel}\0{hashlib.sha256(data).hexdigest()}\n".encode())
    return digest.hexdigest()
