"""Reading the answer out of the JSON a model is still writing.

The assistant's reply is a JSON object (app/ai/chat.py): the lookups it wants, its ``answer``, what
it cites and what it suggests. To show the answer while it is being written, this reads that JSON
a piece at a time, as the provider streams it, and gives back the text of ``answer`` that each
piece completes, with the JSON's escapes (``\\n``, ``\\"``, ``\\u00e9``) already undone, whichever
way the pieces cut it: in the middle of a word, of an escape or of a pair of surrogates.

It is not a JSON parser. It only follows the object's first level far enough to know which
member it is in, and it trusts the whole to be parsed later, by ``chat.parse``, once it has ended.
"""

from enum import Enum, auto
from string import hexdigits as HEX
from typing import Final


class _In(Enum):
    KEY = auto()
    ANSWER = auto()
    OTHER = auto()


_SIMPLE: Final = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
_HIGH: Final = range(0xD800, 0xDC00)
_LOW: Final = range(0xDC00, 0xE000)
_LOST: Final = "�"


class AnswerReader:
    """Gives the text of the ``answer`` of a JSON object that is fed to it a piece at a time."""

    def __init__(self) -> None:
        self._depth = 0
        self._string: _In | None = None
        # After a backslash: "" just after it, and "u" and what follows while a \\u is read.
        self._escape: str | None = None
        self._high = 0
        self._chars: list[str] = []
        self._expect_key = False
        self._key: str | None = None
        self._value_next = False
        #: The model asked to look something up, so what it writes as an answer is not one.
        self.looking_up = False
        #: The answer has been read to its end.
        self.answered = False

    def feed(self, piece: str) -> str:
        """What the answer says in this piece, or an empty string where there is none."""
        written: list[str] = []
        for char in piece:
            if self._string is None:
                self._outside(char)
            else:
                written.append(self._inside(char))
        return "".join(written)

    # -- outside a string

    def _outside(self, char: str) -> None:
        if char.isspace():
            return
        value_starts = self._value_next and self._depth == 1
        self._value_next = False
        if char == '"':
            self._begin_string(value_starts)
        elif char in "{[":
            self._depth += 1
            if self._depth == 1:
                self._expect_key = True
            elif self._depth == 3 and char == "{" and self._key == "lookups":
                self.looking_up = True
        elif char in "}]":
            self._depth -= 1
        elif self._depth == 1 and char == ":":
            self._value_next = True
        elif self._depth == 1 and char == ",":
            self._expect_key = True
            self._key = None

    def _begin_string(self, value_starts: bool) -> None:
        if self._depth == 1 and self._expect_key:
            self._string = _In.KEY
            self._chars = []
        elif value_starts and self._key == "answer":
            self._string = _In.ANSWER
        else:
            self._string = _In.OTHER

    # -- inside one

    def _inside(self, char: str) -> str:
        if self._escape is not None:
            return self._escaped(char)
        if char == "\\":
            self._escape = ""
            return ""
        if char == '"':
            self._end_string()
            return ""
        return self._keep(char)

    def _end_string(self) -> None:
        if self._string is _In.KEY:
            self._key = "".join(self._chars)
            self._expect_key = False
        elif self._string is _In.ANSWER:
            self.answered = True
        self._string = None
        self._high = 0

    def _escaped(self, char: str) -> str:
        escape = self._escape or ""
        if escape == "" and char != "u":
            self._escape = None
            return self._keep(_SIMPLE.get(char, char))
        escape += char
        if len(escape) < 5:
            self._escape = escape
            return ""
        self._escape = None
        digits = escape[1:]
        return (
            self._keep_code(int(digits, 16))
            if all(digit in HEX for digit in digits)
            else self._keep(_LOST)
        )

    def _keep_code(self, code: int) -> str:
        """A character written as \\uXXXX. A pair of them makes one character above U+FFFF, so a
        first half waits for its second."""
        if code in _LOW and self._high:
            pair = 0x10000 + ((self._high - 0xD800) << 10) + (code - 0xDC00)
            self._high = 0
            return self._keep(chr(pair))
        if code in _HIGH:
            lost = self._keep("")
            self._high = code
            return lost
        return self._keep(_LOST if code in _LOW else chr(code))

    def _keep(self, text: str) -> str:
        """What a character of the string comes to: the answer's text is given back, a key's is
        kept to say which member it is, and the rest is not wanted."""
        if self._high:
            text = _LOST + text
            self._high = 0
        if self._string is _In.KEY:
            self._chars.append(text)
        elif self._string is _In.ANSWER and not self.looking_up:
            return text
        return ""
