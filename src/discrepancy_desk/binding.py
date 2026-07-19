from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

BINDING_VERSION = 1


@dataclass(frozen=True)
class RevisionBundle:
    platform: str
    owned_account_id: str
    authored_text: str
    links: tuple[str, ...] = ()
    media: tuple[tuple[str, str], ...] = ()
    alt_texts: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()


def binding_bytes(bundle: RevisionBundle) -> bytes:
    payload = {
        "binding_version": BINDING_VERSION,
        "platform": bundle.platform,
        "owned_account_id": bundle.owned_account_id,
        "authored_text_utf8_hex": bundle.authored_text.encode("utf-8").hex(),
        "links": list(bundle.links),
        "media": [list(item) for item in bundle.media],
        "alt_texts": list(bundle.alt_texts),
        "labels": list(bundle.labels),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def revision_binding(bundle: RevisionBundle) -> str:
    return hashlib.sha256(binding_bytes(bundle)).hexdigest()
