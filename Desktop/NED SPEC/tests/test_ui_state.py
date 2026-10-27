"""The chat belongs to one part, not to the browser tab.

These test the exact functions app.py calls, so the guarantee holds even though the UI
itself is not run here: switching A -> B -> A must show A's own conversation again, and the
analysis cache must notice that the folder's files changed.
"""

from __future__ import annotations

import os
import time

from src.ui_state import (CHAT_KEY, append_turn, clear_history, file_stamp, get_history,
                          history_key)


def answer(text: str) -> dict:
    return {"text": text, "mode": "llm", "model": "fake", "v_ok": True, "v_msg": ""}


# ------------------------------------------------------------------ keys
def test_a_different_part_gets_a_different_key():
    assert history_key("/data", "3004") != history_key("/data", "3005")


def test_the_same_part_in_a_different_folder_gets_a_different_key():
    assert history_key("/data/a", "3004") != history_key("/data/b", "3004")


def test_padding_and_case_of_the_part_number_do_not_start_a_new_chat():
    assert history_key("/data", "3004") == history_key("/data", " 3004 ")
    assert history_key("/data", "AB-12") == history_key("/data", "ab-12")


# ------------------------------------------------------------------ history
def test_switching_parts_keeps_the_conversations_apart_and_restores_the_first():
    state: dict = {}
    a, b = history_key("/data", "A"), history_key("/data", "B")

    append_turn(state, a, "What material is A?", answer("Brass [Excel: a.xlsx, B2]"))
    assert len(get_history(state, a)) == 2
    assert get_history(state, b) == []                  # B starts empty

    append_turn(state, b, "What material is B?", answer("PA6 [Excel: b.xlsx, C3]"))
    assert [m["text"] for m in get_history(state, b)] == ["What material is B?",
                                                          "PA6 [Excel: b.xlsx, C3]"]

    back = get_history(state, a)                         # going back to A restores A only
    assert [m["text"] for m in back] == ["What material is A?", "Brass [Excel: a.xlsx, B2]"]
    assert all("PA6" not in m["text"] for m in back)     # nothing about B leaked in


def test_clear_chat_empties_one_part_and_leaves_the_others():
    state: dict = {}
    a, b = history_key("/data", "A"), history_key("/data", "B")
    append_turn(state, a, "q1", answer("a1"))
    append_turn(state, b, "q2", answer("a2"))
    clear_history(state, a)
    assert get_history(state, a) == []
    assert len(get_history(state, b)) == 2


def test_an_untouched_part_never_sees_another_parts_history():
    """The only way to read history is by key, so a wrong key cannot borrow a conversation."""
    state: dict = {}
    append_turn(state, history_key("/data", "A"), "secret about A", answer("only A"))
    store = state[CHAT_KEY]
    assert len(store) == 1
    assert get_history(state, history_key("/data", "B")) == []
    assert list(store.values())[0][1]["text"] == "only A"


# ------------------------------------------------------------------ cache stamp
def _write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_the_stamp_is_stable_while_the_files_are_untouched(tmp_path):
    _write(tmp_path / "records" / "a.xlsx", "part_number,material\n3004,Brass\n")
    _write(tmp_path / "3004.pdf", "MATERIAL Brass")
    assert file_stamp(tmp_path) == file_stamp(tmp_path)


def test_editing_a_file_changes_the_stamp(tmp_path):
    target = tmp_path / "a.xlsx"
    _write(target, "one")
    before = file_stamp(tmp_path)
    _write(target, "two, and longer than before")
    assert file_stamp(tmp_path) != before

    # same length this time: only the modified-time can tell the two writes apart, so set
    # it explicitly - a filesystem with coarse timestamps would otherwise pass silently.
    same = tmp_path / "b.xlsx"
    _write(same, "AAA")
    after_size_change = file_stamp(tmp_path)
    _write(same, "BBB")
    now = time.time_ns() + 5 * 10**9
    os.utime(same, ns=(now, now))
    assert file_stamp(tmp_path) != after_size_change


def test_adding_a_file_changes_the_stamp(tmp_path):
    _write(tmp_path / "a.xlsx", "one")
    before = file_stamp(tmp_path)
    _write(tmp_path / "3004  rev C.pdf", "MATERIAL Brass")
    assert file_stamp(tmp_path) != before


def test_a_folder_that_is_not_there_has_its_own_stamp(tmp_path):
    assert file_stamp(tmp_path / "nope") == "missing"


def test_office_lock_files_and_unrelated_types_do_not_invalidate_the_cache(tmp_path):
    _write(tmp_path / "a.xlsx", "one")
    before = file_stamp(tmp_path)
    _write(tmp_path / "~$a.xlsx", "lock")
    _write(tmp_path / "notes.md", "not a part file")
    assert file_stamp(tmp_path) == before
