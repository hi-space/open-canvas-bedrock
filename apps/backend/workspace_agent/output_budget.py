"""Reserve model output before dispatch, including every parallel section call."""
import threading
import time


class OutputBudgetExceeded(ValueError):
    """The invocation cannot fund another model call."""


class OutputTokenBudget:
    def __init__(self, limit):
        if type(limit) is not int or limit < 1:
            raise ValueError("The output limit must be a positive integer.")
        self._limit = limit
        self._spent = 0
        self._reserved = 0
        self._closed = False
        self._condition = threading.Condition()

    @property
    def remaining(self):
        with self._condition:
            return 0 if self._closed else max(0, self._limit - self._spent - self._reserved)

    def _reserve(self, maximum, deadline, holdback, allow_partial):
        if type(maximum) is not int or maximum < 1 or type(holdback) is not int or holdback < 0:
            raise ValueError("Invalid model output reservation.")
        with self._condition:
            while True:
                if self._closed:
                    raise OutputBudgetExceeded("The model output limit was reached. Request a smaller edit.")
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    raise OutputBudgetExceeded("The model call deadline was reached.")
                available = self._limit - self._spent - self._reserved - holdback
                if available >= maximum or (allow_partial and available > 0):
                    amount = min(maximum, available)
                    self._reserved += amount
                    return amount
                minimum = 1 if allow_partial else maximum
                if not self._reserved or self._limit - self._spent - holdback < minimum:
                    raise OutputBudgetExceeded("The model output limit was reached. Request a smaller edit.")
                # Another call may return fewer tokens than its reserved maximum.
                self._condition.wait(timeout=timeout)

    def _settle(self, reservation, response):
        usage = response.get("usage") if isinstance(response, dict) else None
        tokens = usage.get("outputTokens") if isinstance(usage, dict) else None
        overrun = type(tokens) is int and tokens > reservation
        # Empty/invalid accounting and uncertain failures never fund more calls.
        charged = tokens if type(tokens) is int and tokens > 0 else reservation
        with self._condition:
            self._reserved -= reservation
            self._spent += charged
            self._closed = self._closed or overrun
            self._condition.notify_all()
        if overrun:
            raise OutputBudgetExceeded("The model exceeded its reserved output limit.")

    def converse(self, provider, *, deadline, holdback=0, allow_partial=False, **request):
        configuration = request.get("inferenceConfig", {})
        reservation = self._reserve(configuration.get("maxTokens"), deadline, holdback, allow_partial)
        bounded = {**request, "inferenceConfig": {**configuration, "maxTokens": reservation}}
        try:
            response = provider(**bounded)
        except BaseException:
            self._settle(reservation, None)
            raise
        self._settle(reservation, response)
        return response
