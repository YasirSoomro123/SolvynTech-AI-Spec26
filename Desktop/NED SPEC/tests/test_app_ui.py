"""Tests for the Streamlit screen itself, driven by streamlit.testing (no browser).

The folder under test is always the generated corpus or a folder the test builds in tmp -
never data/, which belongs to the user. The language model is switched off in every test so
the suite stays offline and deterministic; what the app then says must still be honest.
"""

from __future__ import annotations

import shutil

from streamlit.testing.v1 import AppTest

APP = "app.py"
OK = "\u2705"
WARN = "\u26a0\ufe0f"
INFO = "\u2139\ufe0f"


def named(at: AppTest, label: str):
    """Widget lookup by visible label: AppTest orders inputs by key, not by screen order."""
    hits = [i for i in at.text_input if i.label == label]
    assert hits, [i.label for i in at.text_input]
    return hits[0]


def boot(folder: str, part: str | None = None, llm: bool = False,
         open_maya: bool = True) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    named(at, "Data folder").set_value(folder)
    at.toggle[0].set_value(llm)
    if part is not None:
        at.selectbox[0].select(part)
    at.run()
    if part is not None and open_maya:
        toggle = [b for b in at.button if b.label == "Chat with Maya, the assistant"]
        assert toggle, [b.label for b in at.button]
        toggle[0].set_value(True).run()
    return at


def ask(at: AppTest, question: str) -> AppTest:
    at.chat_input[0].set_value(question).run()
    return at


def clean(at: AppTest) -> list[str]:
    return [e.value for e in at.exception] + [e.value for e in at.error]


def screen(at: AppTest) -> str:
    """Everything the screen says. An element click also reruns the app, so this text can
    hold one screen from before the click; tests use it for what appears, never for what a
    button removed."""
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [w.value for w in at.warning] + [w.value for w in at.info]
    return " ".join(parts)


def history(at: AppTest) -> dict[str, list[dict]]:
    return at.session_state["chat_history"]


class TestStartScreen:
    def test_no_part_is_preselected(self, synth_dir):
        at = boot(str(synth_dir))
        assert clean(at) == []
        assert at.selectbox[0].value is None
        assert "part number" in (at.selectbox[0].placeholder or "").lower()

    def test_the_welcome_state_is_shown_and_nothing_else(self, synth_dir):
        at = boot(str(synth_dir))
        text = screen(at)
        assert "1. Open a folder" in text.replace("<h4>", " ") or "Open a folder" in text
        assert "Level 3" in text
        assert at.tabs == []                 # no numbers on screen before a part is chosen
        assert at.chat_message == []

    def test_every_part_in_the_folder_is_offered(self, synth_dir):
        at = boot(str(synth_dir))
        assert {"3001", "3002", "3003"} <= set(at.selectbox[0].options)


class TestPartScreen:
    def test_choosing_a_part_opens_the_panels_and_the_greeting(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        assert clean(at) == []
        assert [t.label for t in at.tabs] == ["Cross-check", "Part report", "Views",
                                              "Compare", "Extracted facts", "Warnings"]
        greet = at.chat_message[0].markdown[0].value
        assert "3002" in greet and "Excel" in greet and "IGES" in greet

    def test_the_ask_tab_is_gone_and_the_floating_assistant_holds_the_chat(self, synth_dir):
        at = boot(str(synth_dir), "3002", open_maya=False)
        assert "Ask" not in [t.label for t in at.tabs]
        assert at.chat_input == []          # nothing is asked until Maya is opened
        toggle = [b for b in at.button if b.label == "Chat with Maya, the assistant"]
        assert toggle
        toggle[0].set_value(True).run()
        assert clean(at) == []
        assert at.chat_input and "3002" in at.chat_message[0].markdown[0].value

    def test_the_level_badge_counts_the_sources_this_part_has(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        assert "Level 3 data available for part 3002" in screen(at)

    def test_the_level_badge_stops_at_what_the_files_support(self, synth_dir, tmp_path):
        """Excel only, so the drawing and model levels must not be claimed as reached."""
        record = next(p for p in synth_dir.rglob("*")
                      if p.suffix.lower() in (".xlsx", ".xlsm", ".csv") and "3002" in p.name)
        only = tmp_path / "excel-only"
        only.mkdir()
        shutil.copy(record, only / record.name)
        at = boot(str(only), "3002")
        assert clean(at) == []
        text = screen(at)
        assert "Level 1 data available for part 3002" in text
        assert "not reached" in text
        assert "no PDF facts for this part" in text and "no IGES facts for this part" in text

    def test_the_data_folder_is_shown_on_screen(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        assert "Data folder" in screen(at)

    def test_the_about_panel_lists_levels_and_the_guessing_rules(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        text = screen(at)
        assert "How this app avoids guessing" in text
        assert "Numbers come from the files, not from the model" in text
        assert OK in text and WARN not in text        # this part has all three sources

    def test_a_part_missing_a_source_is_marked_as_such(self, synth_dir, tmp_path):
        record = next(p for p in synth_dir.rglob("*")
                      if p.suffix.lower() in (".xlsx", ".xlsm", ".csv") and "3002" in p.name)
        only = tmp_path / "excel-only"
        only.mkdir()
        shutil.copy(record, only / record.name)
        at = boot(str(only), "3002")
        assert WARN in screen(at)

    def test_an_unknown_number_gets_a_friendly_card_not_a_number(self, synth_dir):
        at = boot(str(synth_dir))
        at.selectbox[0].select("+ type a part number that is not listed")
        at.run()
        named(at, "Part number").set_value("3999")
        at.run()
        assert clean(at) == []
        text = screen(at)
        assert "3999 is not in this folder" in text
        assert at.tabs == []                       # nothing was invented for it

    def test_the_nearest_numbers_are_suggested(self, synth_dir):
        at = boot(str(synth_dir))
        at.selectbox[0].select("+ type a part number that is not listed")
        at.run()
        named(at, "Part number").set_value("3009")      # one digit off 3001..3005, no record
        at.run()
        assert "close to what you typed" in screen(at)


class TestChat:
    def test_an_answer_quotes_its_sources_and_offers_evidence(self, synth_dir):
        at = ask(boot(str(synth_dir), "3002"), "What material is it?")
        assert clean(at) == []
        answer = at.chat_message[-1]
        text = answer.markdown[0].value
        assert "extracted from Excel" in text or "[Excel" in text
        assert any(e.label.startswith("Evidence") for e in answer.expander)
        assert "qd-src-excel" in " ".join(m.value for m in answer.markdown)
        assert any("Code answer" in c.value for c in answer.caption)

    def test_an_unanswerable_question_is_answered_honestly(self, synth_dir):
        at = ask(boot(str(synth_dir), "3002"), "What is the weather today?")
        assert clean(at) == []
        assert "can't find" in at.chat_message[-1].markdown[0].value
        assert "Not found in the files" in screen(at)

    def test_each_part_keeps_its_own_conversation(self, synth_dir):
        at = ask(boot(str(synth_dir), "3002"), "What material is it?")
        turns = sum(len(v) for v in history(at).values())
        assert turns == 2                                   # one question and its answer
        at.selectbox[0].select("3003")
        at.run()
        assert clean(at) == []
        assert "3003" in at.chat_message[0].markdown[0].value
        assert all(len(v) == 2 for k, v in history(at).items()
                   if len(v))                               # the other part is untouched
        assert any(len(v) == 0 for v in history(at).values())

    def test_clear_chat_empties_this_part_only(self, synth_dir):
        at = ask(boot(str(synth_dir), "3002"), "What material is it?")
        [b for b in at.button if b.label == "Clear chat"][0].set_value(True).run()
        assert clean(at) == []
        assert all(len(v) == 0 for v in history(at).values())

    def test_the_rating_is_stored_for_the_answer(self, synth_dir):
        at = ask(boot(str(synth_dir), "3002"), "What material is it?")
        [b for b in at.button if b.label == "Helpful"][0].set_value(True).run()
        assert clean(at) == []
        turns = [m for v in history(at).values() for m in v if m["role"] == "assistant"]
        assert turns and turns[0].get("rating") == 1

    def test_the_chat_can_be_downloaded_as_markdown(self, synth_dir):
        at = ask(boot(str(synth_dir), "3002"), "What material is it?")
        labels = [d.label for d in at.get("download_button")]
        assert any(".md" in l for l in labels), labels

    def test_the_suggested_questions_ask_for_what_this_part_has(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        labels = [b.label for b in at.button if b.label.endswith("?")]
        assert labels
        assert not any("price" in l.lower() or "weight" in l.lower() for l in labels)


class TestCrossCheckPanel:
    def test_the_table_shows_unit_difference_and_tolerance(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        df = at.dataframe[0].value
        for column in ("Unit", "Difference", "Tolerance used", "Result"):
            assert column in df.columns, column
        assert set(df[""].dropna()) <= {OK, WARN, INFO}

    def test_the_table_can_be_downloaded_as_csv(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        labels = [d.label for d in at.get("download_button")]
        assert any(".csv" in l for l in labels), labels

    def test_a_plain_sentence_states_the_disagreements(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        assert "checks agree" in screen(at)


def box(at: AppTest, label: str):
    hits = [s for s in at.selectbox if s.proto.label == label]
    assert hits, [s.proto.label for s in at.selectbox]
    return hits[0]


def downloads(at: AppTest) -> list[str]:
    return [d.label for d in at.get("download_button")]


class TestPartReport:
    def test_the_report_page_is_on_screen_and_downloadable(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        text = screen(at)
        assert "Part 3002 - record, drawing and model report" in text
        assert "Where the files disagree" in text
        assert "Download report (.md)" in downloads(at)
        assert "Download report (.pdf)" in downloads(at)

    def test_the_report_says_the_model_did_not_write_it(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        assert "Every number above was produced by the parsers" in screen(at)


class TestDataQuality:
    def test_a_progress_bar_scores_the_part_and_names_a_reason(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        bars = at.get("progress")
        assert len(bars) == 1
        assert 0 < bars[0].value <= 100
        assert "Data quality for this part" in screen(at)

    def test_a_thinner_folder_scores_lower_and_says_which_file_is_missing(self, synth_dir,
                                                                          tmp_path):
        record = next(p for p in synth_dir.rglob("*")
                      if p.suffix.lower() in (".xlsx", ".xlsm", ".csv") and "3002" in p.name)
        only = tmp_path / "excel-only"
        only.mkdir()
        shutil.copy(record, only / record.name)
        full = boot(str(synth_dir), "3002")
        thin = boot(str(only), "3002")
        assert thin.get("progress")[0].value < full.get("progress")[0].value
        assert "no PDF facts" in screen(thin) or "no IGES facts" in screen(thin)


class TestViews:
    def test_the_drawing_page_is_rendered_from_the_file(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        assert len(at.get("imgs")) == 1
        assert "Zoom" in [s.label for s in at.slider]

    def test_the_model_is_shown_as_a_labelled_envelope_not_a_render(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        svg = " ".join(m.value for m in at.markdown if "<svg" in m.value)
        assert "Approximate envelope" in svg
        # the three sizes come from the reader, and the labels refuse to name an axis
        assert "longest edge" in svg and "third edge" in svg
        assert "X axis" not in svg

    def test_a_part_without_a_drawing_says_so_instead_of_showing_something(self, synth_dir,
                                                                          tmp_path):
        record = next(p for p in synth_dir.rglob("*")
                      if p.suffix.lower() in (".xlsx", ".xlsm", ".csv") and "3002" in p.name)
        only = tmp_path / "excel-only"
        only.mkdir()
        shutil.copy(record, only / record.name)
        at = boot(str(only), "3002")
        assert at.get("imgs") == []
        assert "No PDF drawing was matched to this part" in screen(at)
        assert "No IGES model was matched to this part" in screen(at)


class TestCompare:
    def test_nothing_is_compared_until_a_second_number_is_picked(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        assert "until a second number is picked" in screen(at)
        assert not [d.value for d in at.dataframe if "Verdict" in getattr(d.value, "columns", [])]

    def test_picking_a_second_part_produces_a_field_by_field_table(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        box(at, "Compare with").select("3003")
        at.run()
        assert clean(at) == []
        dfs = [d.value for d in at.dataframe if "Verdict" in getattr(d.value, "columns", [])]
        assert dfs, [list(d.value.columns) for d in at.dataframe]
        df = dfs[0]
        assert {c for c in df.columns if c.startswith("Part ")} == {"Part 3002", "Part 3003"}
        assert set(df["Verdict"]) <= {"same", "different", "only one part states it", "-"}
        # the two ideas must not be confused on screen
        assert "not a conflict" in screen(at)

    def test_the_comparison_can_be_downloaded(self, synth_dir):
        at = boot(str(synth_dir), "3002")
        box(at, "Compare with").select("3003")
        at.run()
        assert "Download comparison (.csv)" in downloads(at), downloads(at)
