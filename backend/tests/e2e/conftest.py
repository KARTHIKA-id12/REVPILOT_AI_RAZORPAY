"""Re-exports fixtures owned by the integration suites so the e2e layer
can reuse the same realistic merchant/cart setup instead of duplicating
it. Without this file, pytest cannot see a fixture defined in a
different test module -- fixture visibility is scoped to the defining
module plus any conftest.py above it in the directory tree, never
sideways across sibling modules. This was a real bug found during audit:
both tests in test_complete_flows.py errored at setup on every run
("fixture 'full_loop_merchant' not found" / "fixture 'buyer_cart' not
found") because the fixtures they depend on live in
tests/integration/test_full_orchestrator_loop.py and
tests/integration/test_ai_buyer_checkout.py respectively, with nothing
bridging the two directories.
"""
from tests.integration.test_ai_buyer_checkout import buyer_cart  # noqa: F401
from tests.integration.test_full_orchestrator_loop import full_loop_merchant  # noqa: F401
