"""Pre-filter posts to quickly identify non-events before full analysis."""

from datetime import datetime
from calendar_sync.claude import local_time_str, TIME_ZONE

from anthropic import Anthropic
from anthropic.types import TextBlock

from .models import RssPost

PREFILTER_INPUT_COST_PER_M = 3.00
PREFILTER_OUTPUT_COST_PER_M = 15.00
PREFILTER_MODEL = "claude-sonnet-4-6"

PREFILTER_PROMPT = f"""You are a binary classifier. Given an RSS post from a cycling community social account, determine if the post could plausibly be announcing an event (a ride, meetup, race, social gathering, etc. with a date/time).

Answer with exactly one word: YES or NO.

- YES means the post could be announcing (or modifying/postponing/canceling/clarifying) an upcoming future-tense event and needs further analysis.
- NO means the post is clearly not an event announcement, or the post is written in past tense about an event that has already happened, and can be safely ignored.

More instructions:
* For the sake of reasoning about relative dates (i.e. "this saturday"), the current date and time is {local_time_str(datetime.now())}. The timezone is {TIME_ZONE}. 
* If the event is referred to in future tense but seems to have happened in the recent past, answer YES.
* If the post has so little content such that you'd probably need to see the images/videos to determine if it's an event, answer YES.

do NOT print ANYTHING OTHER THAN YES or NO.
"""


class PrefilterResult:
    """Result from the pre-filter."""

    def __init__(self, is_likely_event: bool, input_tokens: int, output_tokens: int):
        self.is_likely_event = is_likely_event
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens * PREFILTER_INPUT_COST_PER_M / 1_000_000
            + self.output_tokens * PREFILTER_OUTPUT_COST_PER_M / 1_000_000
        )


def prefilter_post(post: RssPost) -> PrefilterResult:
    """Run a cheap check to see if a post is plausibly an event.

    Returns a PrefilterResult. If is_likely_event is False, the post can be
    short-circuited to "ignore" without running the full Sonnet analysis.
    """
    client = Anthropic()

    user_text = f"""Analyze this RSS post:

Title: {post.title}
Author: {post.author or "Unknown"}
Link: {post.link}
Published: {local_time_str(post.published) if post.published else "Unknown"}

Content:
{post.content}
"""

    response = client.messages.create(
        model=PREFILTER_MODEL,
        max_tokens=8,
        system=PREFILTER_PROMPT,
        messages=[{"role": "user", "content": user_text}],
    )

    first_block = response.content[0]
    assert isinstance(first_block, TextBlock)
    answer = (
        first_block.text.splitlines()[0].strip().upper()
    )  # Get the first line of the response
    is_likely_event = answer != "NO"

    if len(first_block.text) > 3:
        print(
            f"Warning: pre-filter response had more than one message. Using only the first message's text. Full response: {response.content}"
        )

    return PrefilterResult(
        is_likely_event=is_likely_event,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
