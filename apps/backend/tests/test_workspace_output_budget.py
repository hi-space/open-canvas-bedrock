"""All model calls in one invocation share a concurrency-safe output allowance."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time

import pytest

from workspace_agent.output_budget import OutputBudgetExceeded, OutputTokenBudget


def reply(text="Revised.", usage=10):
    return {
        "stopReason": "end_turn",
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "usage": {"outputTokens": usage},
    }


def call(budget, provider, maximum=30, **options):
    return budget.converse(
        provider, deadline=time.monotonic() + 3,
        inferenceConfig={"maxTokens": maximum}, **options,
    )


def test_verified_unused_tokens_can_fund_later_calls_but_not_a_new_full_budget():
    budget = OutputTokenBudget(100)
    requests = []
    usages = iter([20, 40, 10])

    def provider(**request):
        requests.append(request["inferenceConfig"]["maxTokens"])
        return reply(usage=next(usages))

    call(budget, provider, 60)
    call(budget, provider, 60)
    with pytest.raises(OutputBudgetExceeded):
        call(budget, provider, 60)
    call(budget, provider, 60, allow_partial=True)
    assert requests == [60, 60, 40]
    assert budget.remaining == 30


def test_parallel_calls_reserve_their_full_maxima_and_wait_for_released_tokens():
    budget = OutputTokenBudget(60)
    release = threading.Event()
    requested = threading.Event()
    two_started = threading.Event()
    third_started = threading.Event()
    lock = threading.Lock()
    attempts, calls, active, peak = 0, 0, 0, 0

    def provider(**request):
        nonlocal calls, active, peak
        maximum = request["inferenceConfig"]["maxTokens"]
        with lock:
            calls += 1
            active += maximum
            peak = max(peak, active)
            if calls == 2:
                two_started.set()
            if calls == 3:
                third_started.set()
        assert release.wait(2)
        with lock:
            active -= maximum
        return reply(usage=10)

    def invoke():
        nonlocal attempts
        with lock:
            attempts += 1
            if attempts == 3:
                requested.set()
        return call(budget, provider)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(invoke) for _ in range(3)]
        try:
            assert requested.wait(2) and two_started.wait(2)
            assert not third_started.wait(0.05)
        finally:
            release.set()
        for future in futures:
            assert future.result(timeout=2)["stopReason"] == "end_turn"
    assert calls == 3
    assert peak <= 60
    assert budget.remaining == 30


@pytest.mark.parametrize("usage", [None, {}, {"outputTokens": None},
                                  {"outputTokens": -1}, {"outputTokens": True},
                                  {"outputTokens": 0}, {"outputTokens": 1.5},
                                  {"outputTokens": "10"}])
def test_missing_or_invalid_usage_charges_the_entire_reservation(usage):
    budget = OutputTokenBudget(60)
    requests = []

    def provider(**request):
        requests.append(request)
        return {**reply(), "usage": usage}

    call(budget, provider)
    call(budget, provider)
    with pytest.raises(OutputBudgetExceeded):
        call(budget, provider)
    assert len(requests) == 2
    assert budget.remaining == 0


def test_an_uncertain_provider_failure_does_not_release_its_reserved_budget():
    budget = OutputTokenBudget(30)
    requests = []

    def provider(**request):
        requests.append(request)
        raise RuntimeError("response lost after inference")

    with pytest.raises(RuntimeError, match="response lost"):
        call(budget, provider)
    with pytest.raises(OutputBudgetExceeded):
        call(budget, provider)
    assert len(requests) == 1


def test_usage_above_the_requested_maximum_closes_the_budget():
    budget = OutputTokenBudget(60)
    requests = []

    def provider(**request):
        requests.append(request)
        return reply(usage=31)

    with pytest.raises(OutputBudgetExceeded):
        call(budget, provider)
    with pytest.raises(OutputBudgetExceeded):
        call(budget, provider, 1)
    assert len(requests) == 1


def test_section_retries_share_the_budget_and_leave_room_for_a_final_reply(monkeypatch):
    from workspace_agent.revise import revise_sections

    monkeypatch.setattr("workspace_agent.revise.MAX_SECTION_TOKENS", 20)
    budget = OutputTokenBudget(50)
    requests = []
    answers = iter(["Rejected.", "Revised."])
    deadline = time.monotonic() + 3

    def provider(**request):
        requests.append(json.loads(request["messages"][0]["content"][0]["text"]))
        return reply(next(answers), usage=20)

    def validate(_before, after):
        if after == "Rejected.":
            raise ValueError("Keep the existing citation.")

    revised, unchanged = revise_sections(
        ["First.", "Second."], "Revise.", validate=validate, deadline=deadline, workers=1,
        converse=lambda **request: budget.converse(
            provider, deadline=deadline, holdback=10, **request,
        ),
    )
    assert revised == ["Revised.", "Second."]
    assert unchanged == [2]
    assert len(requests) == 2
    assert requests[1]["rejected"] == "Keep the existing citation."
    final_requests = []

    def finish(**request):
        final_requests.append(request["inferenceConfig"]["maxTokens"])
        return reply("One section is unchanged.", usage=5)

    call(budget, finish, 20, allow_partial=True)
    assert final_requests == [10]
    assert budget.remaining == 5


def test_waiting_for_an_inflight_reservation_respects_the_deadline():
    budget = OutputTokenBudget(30)
    entered = threading.Event()
    release = threading.Event()

    def provider(**_request):
        entered.set()
        assert release.wait(2)
        return reply(usage=10)

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(call, budget, provider)
        try:
            assert entered.wait(2)
            with pytest.raises(OutputBudgetExceeded):
                budget.converse(
                    lambda **_request: pytest.fail("Expired call reached the provider"),
                    deadline=time.monotonic() + 0.02,
                    inferenceConfig={"maxTokens": 30},
                )
        finally:
            release.set()
        first.result(timeout=2)
