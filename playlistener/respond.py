import random
from typing import Sequence


class Responder:
    """Chooses messages randomly, avoids repeating."""

    last_index = -1
    choices: Sequence[str]

    def __init__(self, choices: Sequence[str]):
        """Set choices."""

        self.choices = choices

    def next(self) -> str:
        """Return the next response."""

        index = random.randint(0, len(self.choices) - 1)
        if index == self.last_index:
            index = (index + 1) % len(self.choices)
        self.last_index = index
        return self.choices[index]

