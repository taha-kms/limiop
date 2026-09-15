"""HTTP access to the Jobicy remote-jobs API.

This module owns transport only. It returns untrusted provider payloads and
never inspects a job field, so validation and normalization stay testable
without a network.
"""

SOURCE_KEY = "jobicy"
DEFAULT_BASE_URL = "https://jobicy.com/api/v2/remote-jobs"
