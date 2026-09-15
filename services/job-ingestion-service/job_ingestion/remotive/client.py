"""HTTP access to the Remotive remote job API.

This module owns transport only. It returns untrusted provider payloads and
never inspects a job field, so validation and normalization stay testable
without a network.
"""

SOURCE_KEY = "remotive"
DEFAULT_BASE_URL = "https://remotive.com/api/remote-jobs"
