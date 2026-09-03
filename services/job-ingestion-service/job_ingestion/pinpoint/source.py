"""What every Pinpoint module agrees on.

Held apart so the validator, the normalizer, the provider, and the client can
all import it without importing each other.
"""

SOURCE_KEY = "pinpoint"
DISPLAY_NAME = "Pinpoint"
DEFAULT_BASE_URL = "https://pinpointhq.com"

# Above the aggregator. An employer's own board is the better account of its own
# posting, which is what source precedence exists to express.
PRECEDENCE = 20

# The feed never states the company a board's postings belong to, so a guessed
# subdomain can never be confirmed and every discovery outcome is unverifiable
# rather than confirmed. Nothing ships as a default; a deployment names its
# boards in configuration, by a person who looked at the careers page.
DEFAULT_BOARDS: tuple[str, ...] = ()
