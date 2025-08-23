import pytest
import inspect
from hypothesis import given, settings, strategies as st

from app.ws import _ensure_resolved

# Helper to construct nested wrappers around a base value.
# Wrapper types:
#  - "value" : raw value (no wrapper)
#  - "call"  : sync callable that returns the previous value
#  - "async" : an async function (callable) that when called returns the previous value (i.e., returns a coroutine)
#  - "call_async": sync callable that returns a coroutine (awaitable) when invoked
def make_wrapped(value, wrappers):
    current = value
    for w in wrappers:
        if w == "call":
            # sync callable returning current
            def make_fn(cur):
                def fn():
                    return cur
                return fn
            current = make_fn(current)
        elif w == "async":
            # async function (callable) that returns current when awaited
            def make_async_fn(cur):
                async def afunc():
                    return cur
                return afunc
            current = make_async_fn(current)
        elif w == "call_async":
            # sync callable that returns a coroutine (awaitable) when invoked
            def make_call_returning_coro(cur):
                def fn():
                    async def inner():
                        return cur
                    return inner()
                return fn
            current = make_call_returning_coro(current)
        else:
            # raw value - shouldn't happen as wrappers are chosen from supported set,
            # keep as a defensive fallback
            current = current
    return current

# Hypothesis strategy:
# - base value: either text or int
# - wrappers: 0..3 nested wrappers chosen from the 4 wrapper types
wrapper_choices = st.lists(st.sampled_from(["call", "async", "call_async"]), min_size=0, max_size=3)
base_value = st.one_of(st.text(), st.integers())

@settings(max_examples=50)  # ensure >= 25 random cases per project rules
@given(base=base_value, wrappers=wrapper_choices)
@pytest.mark.asyncio
async def test_ensure_resolved_various_wrappings(base, wrappers):
    """
    Ensure _ensure_resolved correctly unwraps mixed sync/async/callable wrappers
    and returns the original base value.
    """
    wrapped = make_wrapped(base, wrappers)
    resolved = await _ensure_resolved(wrapped, max_iter=10)
    # For integers and strings we expect exact equality after resolution
    assert resolved == base

# Also test that passing an already-resolved plain value returns it unchanged
@pytest.mark.asyncio
async def test_ensure_resolved_plain_value():
    assert await _ensure_resolved("plain string") == "plain string"
    assert await _ensure_resolved(12345) == 12345

# Test a more nested handcrafted example mixing callables and async callables
@pytest.mark.asyncio
async def test_ensure_resolved_handcrafted_mix():
    value = "final"
    async def a1():
        return value
    def c1():
        return a1  # callable returning an async function (callable)
    def c2():
        return c1  # nested callable
    resolved = await _ensure_resolved(c2(), max_iter=10)
    assert resolved == value
