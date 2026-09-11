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
