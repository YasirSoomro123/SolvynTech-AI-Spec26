"""The deliverable ships no parts.

The organizers supplied no sample files, so `data/` must stay empty of part data: the
tests generate their own corpus and the app reads whatever folder it is pointed at.
These checks fail loudly if sample files are ever committed back into `data/`, because
that is the difference between "works on our files" and "works on theirs".
"""

from __future__ import annotations

from src.pipeline import build_report

ALLOWED = {"README.md", ".gitkeep"}


def test_the_data_folder_ships_no_sample_parts(repo_root):
    data = repo_root / "data"
    assert data.is_dir(), "data/ must exist so a user has somewhere to put files"
    shipped = {p.name for p in data.iterdir() if p.is_file()}
    assert shipped <= ALLOWED, shipped
    # subfolders are the user's business (data/demo, data/uploads/) - the point is that the
    # repo itself carries no part data at the top of data/


def test_an_empty_folder_is_answered_not_crashed(tmp_path):
    rep = build_report("2280", tmp_path)
    assert not rep.facts
    warns = rep.all_warnings()
    assert warns and "2280" in warns[0]
    assert "parts seen here: none" in warns[0]


def test_a_missing_folder_is_reported_as_a_warning(tmp_path):
    rep = build_report("2280", tmp_path / "nope")
    assert not rep.facts
    assert any("does not exist" in w for w in rep.all_warnings())
