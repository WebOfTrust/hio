# -*- encoding: utf-8 -*-
"""
hio.help.decking module

Support for Deck, TrackedDeck, and CueBox classes

"""
import time
from collections import deque
from typing import Any


class Deck(deque):
    """
    Extends deque to support deque access convenience methods .push and .pull
    to remove confusion  about which side of the deque to use (left or right).

    Extends deque with .push an .pull methods to support a different pattern for
    access. .push does not allow  a value of None to be added to the Deck. This
    enables retrieval  with .pull(emptive=True) which returns None when empty
    instead of raising IndexError. This allows use of the walrus operator on
    a pull to both assign and check for empty. For example:

    deck.extend([False, "", []])  # falsy elements but not None
    stuff = []
    while (x := deck.pull(emptive=True)) is not None:
        stuff.append(x)
    assert stuff == [False, "", []]
    assert not deck

    Local methods:
    .push(x) = add x if x is not None to the right side of deque (like append)
    .pull(x) = remove and return element from left side of deque (like popleft)


    Inherited methods from deque:
    .append(x)             = add x to right side of deque
    .appendleft(x)         = add x to left side of deque
    .clear()               = clear all items from deque leaving it a length 0
    .count(x)              = count the number of deque elements equal to x.
    .extend(iterable)      = append elements of iterable to right side
    .extendleft(iterable)  = append elemets of iterable to left side
                             (this reverses iterable)
    .pop()                 = remove and return element from right side
                              if empty then raise IndexError
    .popleft()             = remove and return element from left side
                              if empty then raise IndexError
    .remove(x)             = remove first occurence of x left to right
                              if not found raise ValueError
    .rotate(n)             = rotate n steps to right if neg rotate to left

    Built in methods supported:
    len(d)
    reversed(d)
    copy.copy(d)
    copy.deepcopy(d)
    subscripts d[0] d[-1]

    Attributes:
    .maxlen  = maximum size of Deck or None if unbounded

    """
    def __repr__(self):
        """
        Custome repr for Deck
        """
        itemreprs = repr(list(self))

        return ("Deck({0})".format(itemreprs))


    def push(self, elem: Any):
        """
        If not None, add elem to right side of deque, Otherwise ignore
        Parameters:
            elem (Any): element to be appended to deck (deque)
        """
        if elem is not None:
            self.append(elem)


    def pull(self, emptive=False):
        """
        Remove and return elem from left side of deque,
        If empty and emptive return None else raise IndexError

        Parameters:
            emptive (bool): True means return None instead of raise IndexError
               when attempt to pull
               False means normal behavior of deque
        """
        try:
            return self.popleft()
        except IndexError:
            if not emptive:
                raise
            return None


class TrackedDeck(Deck):
    """
    Extends Deck with optional cap, lifecycle statistics, and back-pressure.

    Drop-in replacement for Deck. All Deck methods work unchanged.
    Adds cap enforcement, push/pull/drop counters, and high water mark
    tracking to diagnose unbounded growth and imbalanced producer/consumer
    patterns.

    When cap is set and the deck is full, push() silently drops the
    element and increments the drop counter. This prevents unbounded
    memory growth in producer-faster-than-consumer scenarios.

    Parameters:
        cap (int): optional maximum number of elements. None means unbounded.
            Unlike deque's maxlen which discards from the opposite end,
            TrackedDeck's cap drops the incoming element (back-pressure).
        owner (str): optional identifier for this deck (for diagnostics)

    Local methods (in addition to Deck methods):
    .stats    = property returning dict of lifecycle statistics
    .pushed   = total successful pushes
    .pulled   = total successful pulls
    .dropped  = total elements dropped due to cap
    .highwater = maximum observed deck depth

    Example:

    deck = TrackedDeck(cap=100, owner="witness_cues")
    deck.push("event_1")
    deck.push("event_2")
    deck.pull()
    assert deck.stats == {
        "pending": 1,
        "pushed": 2,
        "pulled": 1,
        "dropped": 0,
        "highwater": 2,
        "owner": "witness_cues",
    }

    """

    def __init__(self, iterable=(), cap=None, owner=""):
        """
        Initialize TrackedDeck.

        Parameters:
            iterable: initial elements (passed to deque)
            cap (int): optional maximum size. None means unbounded.
            owner (str): optional identifier for diagnostics
        """
        super().__init__(iterable)
        self._cap = cap
        self._owner = owner
        self._pushed = 0
        self._pulled = 0
        self._dropped = 0
        self._highwater = len(self)

    def __repr__(self):
        """
        Custom repr for TrackedDeck
        """
        itemreprs = repr(list(self))
        return ("TrackedDeck({0})".format(itemreprs))

    def push(self, elem: Any):
        """
        If not None, add elem to right side of deque, Otherwise ignore.
        If cap is set and deck is at capacity, drop element and increment
        drop counter instead of appending (back-pressure).

        Parameters:
            elem (Any): element to be appended to deck (deque)
        """
        if elem is None:
            return
        if self._cap is not None and len(self) >= self._cap:
            self._dropped += 1
            return
        super().push(elem)
        self._pushed += 1
        if len(self) > self._highwater:
            self._highwater = len(self)

    def pull(self, emptive=False):
        """
        Remove and return elem from left side of deque.
        Tracks pull count on successful removal.

        Parameters:
            emptive (bool): True means return None instead of raise IndexError
        """
        result = super().pull(emptive=emptive)
        if result is not None:
            self._pulled += 1
        return result

    @property
    def cap(self):
        """Maximum capacity or None if unbounded"""
        return self._cap

    @property
    def owner(self):
        """Owner identifier for diagnostics"""
        return self._owner

    @property
    def pushed(self):
        """Total successful pushes"""
        return self._pushed

    @property
    def pulled(self):
        """Total successful pulls"""
        return self._pulled

    @property
    def dropped(self):
        """Total elements dropped due to cap"""
        return self._dropped

    @property
    def highwater(self):
        """Maximum observed deck depth"""
        return self._highwater

    @property
    def stats(self):
        """
        Lifecycle statistics as a dict.

        Returns dict with keys:
            pending: current number of elements
            pushed: total successful pushes
            pulled: total successful pulls
            dropped: total elements dropped due to cap
            highwater: maximum observed deck depth
            owner: owner identifier
        """
        return dict(
            pending=len(self),
            pushed=self._pushed,
            pulled=self._pulled,
            dropped=self._dropped,
            highwater=self._highwater,
            owner=self._owner,
        )


class CueBox:
    """
    Two-phase cue lifecycle manager: claim -> resolve | reject.

    Prevents the re-push livelock pattern where unhandled cues bounce
    between Doers indefinitely. A cue must be explicitly claimed before
    processing and either resolved (handled) or rejected (returned to
    pending with retry limit).

    Parameters:
        cap (int): optional cap for the internal pending TrackedDeck
        maxRetries (int): maximum times a cue can be rejected before
            being permanently dropped. Default 3.
        leakTimeout (float): seconds after which a claimed but unresolved
            cue is considered leaked. Default 30.0.

    Local methods:
    .push(cue)              = add cue to pending queue
    .claim(claimer)         = remove from pending, mark as claimed.
                              Returns (cueId, cue) or None.
    .resolve(cueId)         = mark cue as handled (removes from claimed)
    .reject(cueId)          = return cue to pending (respects maxRetries)
    .expireLeaked()         = find and expire timed-out claimed cues
    .stats                  = property returning lifecycle statistics

    Example:

    box = CueBox(cap=256, maxRetries=3)
    box.push({"type": "receipt", "said": "EABC..."})

    claim = box.claim("WitnessPublisher")
    if claim is not None:
        cueId, cue = claim
        try:
            handle(cue)
            box.resolve(cueId)
        except CannotHandle:
            box.reject(cueId)  # returns to pending if retries remain
    """

    def __init__(self, cap=None, maxRetries=3, leakTimeout=30.0):
        """
        Initialize CueBox.

        Parameters:
            cap (int): optional cap for pending queue
            maxRetries (int): max reject cycles before permanent drop
            leakTimeout (float): seconds before claimed cue is leaked
        """
        self._pending = TrackedDeck(cap=cap, owner="CueBox.pending")
        self._claimed = {}  # cueId -> (cue, claimer, claimedAt, retries)
        self._retryCounts = {}  # id(cue) -> cumulative reject count
        self._maxRetries = maxRetries
        self._leakTimeout = leakTimeout
        self._resolved = 0
        self._rejected = 0
        self._expired = 0

    def push(self, cue: Any):
        """
        Add a cue to the pending queue.

        Parameters:
            cue: the cue element (must not be None)
        """
        self._pending.push(cue)

    def claim(self, claimer=""):
        """
        Remove next cue from pending and mark as claimed.

        Preserves cumulative retry count across reject/re-push cycles
        so that maxRetries is enforced over the full lifecycle of a cue.

        Parameters:
            claimer (str): identifier of the claiming Doer

        Returns:
            tuple: (cueId, cue) if a cue was available, None otherwise
        """
        cue = self._pending.pull(emptive=True)
        if cue is None:
            return None
        cueId = id(cue)
        retries = self._retryCounts.get(cueId, 0)
        self._claimed[cueId] = (cue, claimer, time.monotonic(), retries)
        return (cueId, cue)

    def resolve(self, cueId):
        """
        Mark cue as successfully handled. Removes from claimed.

        Parameters:
            cueId: the cue identifier returned by claim()
        """
        entry = self._claimed.pop(cueId, None)
        if entry is not None:
            self._resolved += 1
            self._retryCounts.pop(cueId, None)

    def reject(self, cueId):
        """
        Return cue to pending queue. Respects maxRetries to prevent
        indefinite re-push livelock.

        Retry count is tracked cumulatively across reject/re-push/re-claim
        cycles via identity tracking. If the cue has been rejected
        maxRetries times, it is permanently dropped instead of returned
        to pending.

        Parameters:
            cueId: the cue identifier returned by claim()
        """
        entry = self._claimed.pop(cueId, None)
        if entry is None:
            return
        cue, claimer, claimedAt, retries = entry
        self._rejected += 1
        retries += 1
        if retries < self._maxRetries:
            self._retryCounts[id(cue)] = retries
            self._pending.push(cue)
        else:
            self._retryCounts.pop(id(cue), None)

    def expireLeaked(self):
        """
        Find and expire cues that were claimed but never resolved or
        rejected within leakTimeout seconds.

        Returns:
            list: list of (cueId, cue) tuples that were expired
        """
        now = time.monotonic()
        leaked = []
        for cueId in list(self._claimed):
            cue, claimer, claimedAt, retries = self._claimed[cueId]
            if now - claimedAt > self._leakTimeout:
                self._claimed.pop(cueId)
                self._expired += 1
                leaked.append((cueId, cue))
        return leaked

    @property
    def stats(self):
        """
        Lifecycle statistics as a dict.

        Returns dict with keys:
            pending: current pending count
            claimed: currently claimed count
            resolved: total resolved count
            rejected: total rejected count
            expired: total expired (leaked) count
        """
        return dict(
            pending=len(self._pending),
            claimed=len(self._claimed),
            resolved=self._resolved,
            rejected=self._rejected,
            expired=self._expired,
        )

    def __len__(self):
        """Total cues in flight (pending + claimed)"""
        return len(self._pending) + len(self._claimed)

    def __bool__(self):
        """True if any cues pending or claimed"""
        return bool(self._pending) or bool(self._claimed)
