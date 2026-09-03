"""What every Polymer module agrees on.

Held apart so the validator, the normalizer, the provider, and the client can
all import it without importing each other.
"""

SOURCE_KEY = "polymer"
DISPLAY_NAME = "Polymer"
DEFAULT_BASE_URL = "https://api.polymer.co/v1/hire/organizations"

# Above the aggregator. An employer's own board is the better account of its own
# posting, which is what source precedence exists to express.
PRECEDENCE = 20

# The only slug known to answer is Polymer's own demo organisation, and its
# postings are invented rather than real employer data. Nothing ships as a
# default; a deployment names its boards in configuration.
DEFAULT_BOARDS: tuple[str, ...] = ()
