"""Assertion collector shared by every simulation module."""


class Checks:
    """Collects (ok, label, detail) triples over the whole suite."""

    def __init__(self):
        self.items = []

    def ok(self, cond, label, detail=""):
        """Record one bound."""
        self.items.append((bool(cond), label, detail))
        return bool(cond)

    def fail(self, label, detail=""):
        return self.ok(False, label, detail)

    #reporting
    def n(self):
        return len(self.items)

    def n_ok(self):
        return sum(1 for c, _, _ in self.items if c)

    def failures(self):
        return [(label, detail) for c, label, detail in self.items if not c]

    def all_ok(self):
        return all(c for c, _, _ in self.items)
