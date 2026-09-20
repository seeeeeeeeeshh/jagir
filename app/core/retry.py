from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

# Shared retry policy for flaky Playwright page interactions (timeouts, transient
# navigation errors). Deliberately narrow: we never want to retry on assertion
# failures or parsing bugs, only on network/timeout-shaped exceptions.
#
# playwright.sync_api.TimeoutError does NOT subclass the builtin TimeoutError
# (confirmed: its MRO is Error -> Exception, no relation to builtins.TimeoutError),
# so it must be listed explicitly or this decorator silently never retries the
# exact failure it exists for.
network_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    retry=retry_if_exception_type((TimeoutError, ConnectionError, PlaywrightTimeoutError)),
)
