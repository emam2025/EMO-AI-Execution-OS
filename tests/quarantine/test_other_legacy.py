"""
other_legacy — Pre-existing legacy integration failures not covered by other categories.

These include compliance audit immutability, contracts, e2e pipeline tests,
freeze/release certification, and phase/distributed tests that require full
system wiring not available in the current runtime.

Root cause: Legacy integration tests expecting fully wired composition root.
Estimated effort: 4-6 hours (wire remaining services in composition root).
"""
