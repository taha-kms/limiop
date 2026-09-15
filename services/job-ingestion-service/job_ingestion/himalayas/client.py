"""HTTP access to the Himalayas job board API.

This module owns transport only. It returns untrusted provider payloads and
never inspects a job field, so validation and normalization stay testable
without a network.
"""

SOURCE_KEY = "himalayas"
DEFAULT_BASE_URL = "https://himalayas.app/jobs/api"
