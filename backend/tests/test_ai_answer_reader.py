"""Reading the answer out of JSON that is still being written."""

import json

import pytest

from app.ai.answer_reader import AnswerReader


def read(text: str, size: int | None = None) -> tuple[str, AnswerReader]:
    """What ``text`` says as its answer when it comes ``size`` characters at a time (all at once
    when there is no size)."""
    reader = AnswerReader()
    step = size or len(text) or 1
    return "".join(reader.feed(text[at : at + step]) for at in range(0, len(text), step)), reader


def reply(answer: str, lookups: str = "[]", rest: str = '"cites":[],"actions":[]') -> str:
    return f'{{"lookups":{lookups},"answer":{answer},{rest}}}'


SIZES = [None, 1, 2, 3, 5, 7]


@pytest.mark.parametrize("size", SIZES)
def test_the_answer_is_read_however_the_pieces_cut_it(size: int | None) -> None:
    said = 'Start with [incident 3]: it was "scanned" \\ twice.\nLine é two 😀 \u0001 /'

    got, reader = read(reply(json.dumps(said)), size)

    assert got == said
    assert reader.answered is True
    assert reader.looking_up is False


@pytest.mark.parametrize("size", SIZES)
def test_it_does_not_matter_how_the_json_is_laid_out(size: int | None) -> None:
    text = '{\n  "lookups" : [ ],\n  "answer" :\n "Hi there",\n  "cites": [ "incident 3" ]\n}'

    assert read(text, size)[0] == "Hi there"


@pytest.mark.parametrize("size", SIZES)
def test_what_it_writes_before_it_has_an_answer_is_not_one(size: int | None) -> None:
    lookups = '[{"tool":"incident","id":3,"name":null,"hours":null,"limit":null}]'

    got, reader = read(reply('"It is still looking."', lookups), size)

    assert got == ""
    assert reader.looking_up is True


def test_an_empty_answer_is_an_answer_of_nothing() -> None:
    got, reader = read(reply('""'))

    assert (got, reader.answered) == ("", True)


@pytest.mark.parametrize("size", SIZES)
def test_an_answer_that_is_not_text_is_not_read(size: int | None) -> None:
    got, reader = read(reply("null"), size)

    assert (got, reader.answered) == ("", False)


@pytest.mark.parametrize("size", SIZES)
def test_only_the_answer_of_the_object_is_read(size: int | None) -> None:
    text = (
        '{"cites":["answer"],"actions":[{"kind":"open","answer":"nested","note":"n"}],'
        '"answer":"real","extra":{"answer":"also not"}}'
    )

    assert read(text, size)[0] == "real"


def test_a_name_may_be_written_with_escapes() -> None:
    assert read('{"ans\\u0077er":"Hi"}')[0] == "Hi"


def test_what_comes_after_the_end_of_the_answer_is_left_out() -> None:
    got, _ = read(reply('"Done."', rest='"cites":["x \\"quoted\\""],"actions":[]'))

    assert got == "Done."


@pytest.mark.parametrize("size", SIZES)
def test_a_pair_of_surrogates_is_one_character(size: int | None) -> None:
    assert read('{"answer":"a\\ud83d\\ude00b"}', size)[0] == "a😀b"


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        # A first half with no second half, then an ordinary character, or another first half, or
        # the end of the string.
        ('"\\ud83dx"', "�x"),
        ('"\\ud83d\\ud83d\\ude00"', "�😀"),
        ('"\\ud83d"', ""),
        ('"\\ude00"', "�"),
        ('"\\ud83d\\n"', "�\n"),
        # What isn't four digits of hexadecimal.
        ('"\\u12xz!"', "�!"),
        ('"\\u1_23!"', "�!"),
        ('"\\q\\/\\b\\f\\r\\t"', "q/\b\f\r\t"),
    ],
)
def test_what_is_written_wrongly_is_read_the_way_a_browser_does(
    written: str, expected: str
) -> None:
    assert read(f'{{"answer":{written}}}')[0] == expected
