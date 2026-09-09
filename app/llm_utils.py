import time
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

def call_with_retry(fn, *args, max_retries=5, **kwargs):
    """Retries on 429/503 with exponential backoff — exactly the errors in your usage graph."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except (ResourceExhausted, ServiceUnavailable) as e:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + 1  # 2s, 3s, 5s, 9s, 17s
            print(f"Rate limited, retrying in {wait}s...")
            time.sleep(wait)
