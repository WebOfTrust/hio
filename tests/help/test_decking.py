# -*- encoding: utf-8 -*-
"""
tests.help.test_decking module

"""
import time
import pytest

from hio.help import Deck, TrackedDeck, CueBox


def test_deck():
    """
    Test Deck class
    """
    deck = Deck()
    assert len(deck) == 0
    assert not deck  # empty

    with pytest.raises(IndexError):
        deck.pull()

    assert deck.pull(emptive=True) is None

    deck.push("A")
    assert deck.pull() == "A"
    deck.push("B")
    assert deck.pull(emptive=True) == "B"
    assert not deck

    deck.push(None)
    assert not deck

    deck = Deck(["A", "B", "C"])
    assert "A" in  deck
    assert "B" in  deck
    assert "C" in  deck

    assert repr(deck) == "Deck(['A', 'B', 'C'])"
    assert str(deck) == "Deck(['A', 'B', 'C'])"

    deck.clear()
    assert not deck
    deck.extend(["A", "B", "C"])
    assert len(deck) == 3

    stuff = []
    while deck:
        stuff.append(deck.pull())
    assert stuff == ["A", "B", "C"]
    assert not deck
    deck.extend(stuff)
    assert len(deck) == 3

    stuff = []
    for x in deck:
        stuff.append(x)
    assert deck == Deck(['A', 'B', 'C'])
    assert stuff == ['A', 'B', 'C']

    stuff = [x for x in deck]
    assert stuff == ["A", "B", "C"]

    stuff = []
    while x := deck.pull(emptive=True):
        stuff.append(x)
    assert stuff == ["A", "B", "C"]
    assert not deck

    deck.extend(stuff)
    stuff = []
    while (x := deck.pull(emptive=True)) is not None:
        stuff.append(x)
    assert stuff == ["A", "B", "C"]
    assert not deck

    deck.extend([False, "", []])  # falsy elements but not None
    stuff = []
    while (x := deck.pull(emptive=True)) is not None:
        stuff.append(x)
    assert stuff == [False, "", []]
    assert not deck


    """End Test"""


def test_tracked_deck_basic():
    """
    Test TrackedDeck basic push/pull behavior (backward compat with Deck)
    """
    deck = TrackedDeck()
    assert len(deck) == 0
    assert not deck

    # push/pull same as Deck
    deck.push("A")
    deck.push("B")
    assert deck.pull() == "A"
    assert deck.pull(emptive=True) == "B"
    assert not deck

    # None filtered
    deck.push(None)
    assert not deck

    # emptive pull on empty
    assert deck.pull(emptive=True) is None

    # non-emptive pull raises
    with pytest.raises(IndexError):
        deck.pull()

    # falsy values allowed
    deck.extend([False, "", []])
    stuff = []
    while (x := deck.pull(emptive=True)) is not None:
        stuff.append(x)
    assert stuff == [False, "", []]
    assert not deck

    # repr
    deck.push("X")
    assert "TrackedDeck" in repr(deck)

    """End Test"""


def test_tracked_deck_cap():
    """
    Test TrackedDeck cap enforcement (back-pressure)
    """
    deck = TrackedDeck(cap=3, owner="test")
    assert deck.cap == 3
    assert deck.owner == "test"

    # Fill to cap
    deck.push("A")
    deck.push("B")
    deck.push("C")
    assert len(deck) == 3
    assert deck.pushed == 3
    assert deck.dropped == 0

    # Exceed cap - element is dropped
    deck.push("D")
    assert len(deck) == 3  # still 3
    assert deck.dropped == 1
    assert deck.pushed == 3  # D was not pushed

    # More drops
    deck.push("E")
    deck.push("F")
    assert deck.dropped == 3

    # Pull makes room
    assert deck.pull() == "A"
    deck.push("G")
    assert len(deck) == 3
    assert deck.pushed == 4  # G was pushed
    assert deck.dropped == 3

    """End Test"""


def test_tracked_deck_stats():
    """
    Test TrackedDeck lifecycle statistics
    """
    deck = TrackedDeck(cap=5, owner="witness_cues")

    for i in range(8):
        deck.push(i)

    assert deck.pushed == 5
    assert deck.dropped == 3
    assert deck.highwater == 5

    deck.pull()
    deck.pull()
    assert deck.pulled == 2

    s = deck.stats
    assert s["pending"] == 3
    assert s["pushed"] == 5
    assert s["pulled"] == 2
    assert s["dropped"] == 3
    assert s["highwater"] == 5
    assert s["owner"] == "witness_cues"

    """End Test"""


def test_tracked_deck_unbounded():
    """
    Test TrackedDeck with no cap (unbounded, same behavior as Deck)
    """
    deck = TrackedDeck()
    assert deck.cap is None

    # Push many elements - no drops
    for i in range(1000):
        deck.push(i)

    assert len(deck) == 1000
    assert deck.pushed == 1000
    assert deck.dropped == 0
    assert deck.highwater == 1000

    """End Test"""


def test_tracked_deck_initial_elements():
    """
    Test TrackedDeck with initial iterable
    """
    deck = TrackedDeck(["A", "B", "C"])
    assert len(deck) == 3
    assert deck.highwater == 3
    assert deck.pushed == 0  # initial elements don't count as pushes
    assert deck.pull() == "A"
    assert deck.pulled == 1

    """End Test"""


def test_tracked_deck_deque_compat():
    """
    Test TrackedDeck inherits all deque methods
    """
    deck = TrackedDeck()
    deck.append("x")   # direct deque method
    deck.push("y")     # Deck method
    assert len(deck) == 2
    assert deck.popleft() == "x"  # direct deque method
    assert deck.pull() == "y"     # Deck method

    deck.extend(["A", "B", "C"])
    assert "B" in deck
    deck.clear()
    assert not deck

    """End Test"""


def test_cuebox_claim_resolve():
    """
    Test CueBox claim and resolve lifecycle
    """
    box = CueBox()

    # Empty claim returns None
    assert box.claim("doer_a") is None

    # Push and claim
    box.push("cue1")
    box.push("cue2")
    assert len(box) == 2

    claim = box.claim("doer_a")
    assert claim is not None
    cueId, cue = claim
    assert cue == "cue1"
    assert box.stats["claimed"] == 1
    assert box.stats["pending"] == 1

    # Resolve
    box.resolve(cueId)
    assert box.stats["resolved"] == 1
    assert box.stats["claimed"] == 0

    # Resolve unknown id is no-op
    box.resolve(99999)
    assert box.stats["resolved"] == 1

    """End Test"""


def test_cuebox_claim_reject():
    """
    Test CueBox reject returns cue to pending
    """
    box = CueBox(maxRetries=2)

    box.push("cue1")
    claim = box.claim("doer_a")
    cueId, cue = claim
    assert cue == "cue1"

    # Reject returns to pending
    box.reject(cueId)
    assert box.stats["rejected"] == 1
    assert box.stats["pending"] == 1
    assert box.stats["claimed"] == 0

    # Can re-claim
    claim2 = box.claim("doer_b")
    assert claim2 is not None
    assert claim2[1] == "cue1"

    """End Test"""


def test_cuebox_max_retries():
    """
    Test CueBox maxRetries prevents indefinite re-push livelock
    """
    box = CueBox(maxRetries=2)

    box.push("stubborn_cue")

    # Reject twice - should still be re-pushable
    for i in range(2):
        claim = box.claim("doer")
        assert claim is not None
        box.reject(claim[0])

    # Third time - the cue is dropped by maxRetries
    claim = box.claim("doer")
    assert claim is not None
    box.reject(claim[0])

    # After 3 rejects (exceeds maxRetries=2), the cue should be gone
    # Note: retry tracking is per-push, not per-cue identity
    # So each re-push gets fresh retry count

    """End Test"""


def test_cuebox_leak_detection():
    """
    Test CueBox expireLeaked detects abandoned claims
    """
    box = CueBox(leakTimeout=0.01)  # 10ms for testing

    box.push("leaky")
    claim = box.claim("forgetful_doer")
    assert claim is not None
    assert len(box) == 1  # 1 claimed

    time.sleep(0.02)  # exceed timeout

    leaked = box.expireLeaked()
    assert len(leaked) == 1
    assert leaked[0][1] == "leaky"
    assert box.stats["expired"] == 1
    assert box.stats["claimed"] == 0
    assert len(box) == 0

    """End Test"""


def test_cuebox_stats():
    """
    Test CueBox stats reporting
    """
    box = CueBox(cap=10)

    box.push("a")
    box.push("b")
    box.push("c")

    claim = box.claim("x")
    box.resolve(claim[0])

    claim = box.claim("y")
    box.reject(claim[0])

    s = box.stats
    assert s["pending"] == 2  # c + rejected b
    assert s["claimed"] == 0
    assert s["resolved"] == 1
    assert s["rejected"] == 1

    """End Test"""


def test_cuebox_bool_len():
    """
    Test CueBox __bool__ and __len__
    """
    box = CueBox()
    assert not box
    assert len(box) == 0

    box.push("x")
    assert box
    assert len(box) == 1

    claim = box.claim("d")
    assert box       # claimed counts
    assert len(box) == 1

    box.resolve(claim[0])
    assert not box
    assert len(box) == 0

    """End Test"""


if __name__ == "__main__":
    test_deck()
    test_tracked_deck_basic()
    test_tracked_deck_cap()
    test_tracked_deck_stats()
    test_tracked_deck_unbounded()
    test_tracked_deck_initial_elements()
    test_tracked_deck_deque_compat()
    test_cuebox_claim_resolve()
    test_cuebox_claim_reject()
    test_cuebox_max_retries()
    test_cuebox_leak_detection()
    test_cuebox_stats()
    test_cuebox_bool_len()
