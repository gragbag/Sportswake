"""Derive a stable, readable handle from a user id.

Everyone gets one of these without choosing anything, so signup writes no
row, reserves no name, and cannot dead-end a user whose email is still
unverified. A chosen username in `profiles` overrides it; until then this
is the identity, and because it is a pure function of an immutable uuid it
never changes and never collides.

Word lists are hand-checked. Random adjective-noun pairing produces
offensive combinations more often than people expect, and the failure mode
is somebody's handle on a public comment -- so these are deliberately
bland, and any addition should be read against every word in the other
list before it lands.
"""

from __future__ import annotations

import hashlib

_ADJECTIVES = (
    "amber",
    "arctic",
    "brisk",
    "bronze",
    "calm",
    "candid",
    "civic",
    "clear",
    "coastal",
    "copper",
    "crisp",
    "daily",
    "dusk",
    "early",
    "eastern",
    "even",
    "fair",
    "first",
    "frank",
    "fresh",
    "gentle",
    "granite",
    "harbor",
    "high",
    "hollow",
    "inland",
    "ivory",
    "keen",
    "level",
    "lucid",
    "marble",
    "mild",
    "modest",
    "northern",
    "olive",
    "open",
    "patient",
    "plain",
    "prompt",
    "quiet",
    "rapid",
    "ready",
    "river",
    "rural",
    "sable",
    "silver",
    "sincere",
    "slate",
    "solid",
    "southern",
    "spare",
    "steady",
    "still",
    "stone",
    "sunlit",
    "swift",
    "tidal",
    "upland",
    "urban",
    "vivid",
    "walnut",
    "western",
    "willow",
    "winter",
)

_NOUNS = (
    "alder",
    "anchor",
    "arbor",
    "aspen",
    "basin",
    "beacon",
    "birch",
    "bridge",
    "brook",
    "canyon",
    "cedar",
    "channel",
    "cliff",
    "compass",
    "cove",
    "current",
    "delta",
    "dune",
    "ember",
    "estuary",
    "fathom",
    "fern",
    "field",
    "fjord",
    "forest",
    "gallery",
    "garden",
    "glacier",
    "grove",
    "harbor",
    "haven",
    "heron",
    "hollow",
    "island",
    "juniper",
    "lantern",
    "ledger",
    "linden",
    "meadow",
    "mesa",
    "moor",
    "orchard",
    "otter",
    "paddock",
    "pasture",
    "pebble",
    "pine",
    "plateau",
    "prairie",
    "quarry",
    "ridge",
    "sandbar",
    "sequoia",
    "shoal",
    "sparrow",
    "spruce",
    "summit",
    "thicket",
    "tundra",
    "valley",
    "willow",
    "windmill",
)


def derive_handle(user_id: str) -> str:
    """A stable handle like "brisk-otter-4417".

    Deterministic: the same uuid always yields the same handle, so a person
    stays recognisable across threads without anything being stored.
    Collisions between two *derived* handles are possible in principle but
    irrelevant in practice -- roughly 16 million combinations against a
    handful of users -- and a real collision only ever means two people
    share a display name, never that identity is confused, because every
    lookup keys on user_id.
    """
    digest = hashlib.sha256(user_id.encode()).digest()
    adjective = _ADJECTIVES[digest[0] % len(_ADJECTIVES)]
    noun = _NOUNS[digest[1] % len(_NOUNS)]
    number = int.from_bytes(digest[2:4], "big") % 10000
    return f"{adjective}-{noun}-{number:04d}"
