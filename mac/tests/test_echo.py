from __future__ import annotations

from s2t.core.echo import ECHO_WINDOW_SECONDS, EchoFilter


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _filter():
    clock = Clock()
    return EchoFilter(clock=clock), clock


def test_identical_echo_from_speakers_is_caught():
    # Exact pairs from a live test meeting played through laptop speakers.
    f, _ = _filter()
    f.note_remote("大家好，这是一段系统音频测试。我们讨论第三季度的预算。")
    assert f.is_echo("大家好，这是一段系统音频测试。我们讨论第三季度的预算。")
    f.note_remote("This is a system audio test for the meeting transcriber.")
    assert f.is_echo("This is a system audio test for the meeting transcriber.")


def test_slightly_garbled_echo_is_caught():
    f, _ = _filter()
    f.note_remote("The quarterly numbers look strong, but the launch date is still slipping.")
    assert f.is_echo("the quarterly numbers look strong but launch date is still slipping")


def test_echo_split_across_two_remote_lines_is_caught():
    f, _ = _filter()
    f.note_remote("第一是预算，")
    f.note_remote("第二是排期，第三是人力资源。")
    assert f.is_echo("第一是预算，第二是排期，第三是人力资源。")


def test_users_own_different_sentence_is_kept():
    f, _ = _filter()
    f.note_remote("This is a system audio test for the meeting transcriber.")
    assert not f.is_echo("I think we should move the launch to next quarter.")
    assert not f.is_echo("我们下周再看一下这个结果吧。")


def test_short_replies_are_never_dropped():
    f, _ = _filter()
    f.note_remote("Yes.")
    assert not f.is_echo("Yes.")
    f.note_remote("好的。")
    assert not f.is_echo("好的。")


def test_old_remote_text_expires():
    f, clock = _filter()
    f.note_remote("This is a system audio test for the meeting transcriber.")
    clock.t += ECHO_WINDOW_SECONDS + 1
    assert not f.is_echo("This is a system audio test for the meeting transcriber.")


def test_no_remote_text_means_no_echo():
    f, _ = _filter()
    assert not f.is_echo("This is a system audio test for the meeting transcriber.")
