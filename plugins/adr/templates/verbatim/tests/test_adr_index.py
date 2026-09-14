import json

import adr_vendored_conftest as _cf

load_script = _cf.load_script
run_script = _cf.run_script
write = _cf.write

adr_lib = load_script("adr_lib")
adr_index = load_script("adr_index")


def adr(root, name, **meta):
    body = {"type": "adr", "status": "accepted", "date": "2026-08-13",
            "title": name.split("-", 1)[1].replace(".md", "").replace("-", " ")}
    body.update(meta)
    return write(root / "docs" / "adr" / name,
                 "---\n" + adr_lib.dump_frontmatter(body) + "---\n\n# body\n")


def repo(tmp_path, config=None):
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    write(tmp_path / ".claude" / "adr.json",
          json.dumps(config or {"version": 1, "dir": "docs/adr",
                                "register": "docs/adr/README.md",
                                "id_scheme": "sequential"}))
    return tmp_path


# --- Task 11: the register block builder ------------------------------------

def test_rows_group_by_area_and_carry_the_todo_marker(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order-state-machine.md", area="orders", title="Order state machine")
    adr(root, "0012-gateway-auth.md", area="auth", title="Gateway auth")
    block = adr_index.build_block(adr_lib.load_corpus(root), {})
    assert "### auth" in block and "### orders" in block
    assert block.index("### auth") < block.index("### orders")
    assert ("- [0007 — Order state machine](./0007-order-state-machine.md)"
            " — accepted — <!-- TODO: summary -->") in block
    assert block.splitlines()[0].startswith("<!-- ADR-INDEX:BEGIN")
    assert block.splitlines()[-1] == "<!-- ADR-INDEX:END -->"


def test_an_adr_with_no_area_lands_in_unfiled_last(tmp_path):
    root = repo(tmp_path)
    adr(root, "0001-a.md", area="orders")
    adr(root, "0002-b.md")
    block = adr_index.build_block(adr_lib.load_corpus(root), {})
    assert block.index("### orders") < block.index("### unfiled")


def test_a_superseded_row_names_the_survivor(tmp_path):
    root = repo(tmp_path)
    adr(root, "0031-retry-backoff.md", status="superseded",
        superseded_by=["0088-new.md"], title="Retry backoff")
    adr(root, "0088-new.md", supersedes=["0031-retry-backoff.md"])
    block = adr_index.build_block(adr_lib.load_corpus(root), {})
    assert "— superseded by 0088 —" in block


# --- Task 12: summary preservation, keyed by href ---------------------------

EM = "—"


def register_with(rows):
    return ("# Architecture decisions\n\nHand-authored intro.\n\n"
            + adr_index.BEGIN + "\n" + adr_index.NOTE + "\n\n"
            + "### orders\n" + "\n".join(rows) + "\n\n" + adr_index.END
            + "\n\nHand-authored footer.\n")


def test_a_summary_survives_and_an_em_dash_inside_it_is_kept(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    write(root / "docs" / "adr" / "README.md", register_with([
        f"- [0007 {EM} Order state machine](./0007-order.md) {EM} accepted "
        f"{EM} Keeps orders honest {EM} and auditable",
    ]))
    summaries, unparsed = adr_index.read_rows(
        (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8"))
    assert summaries["./0007-order.md"] == f"Keeps orders honest {EM} and auditable"
    assert unparsed == []


def test_a_row_whose_href_no_longer_resolves_is_dropped_into_the_receipt(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    write(root / "docs" / "adr" / "README.md", register_with([
        f"- [0007 {EM} Order state machine](./0007-order.md) {EM} accepted {EM} kept",
        f"- [0099 {EM} Gone](./0099-gone.md) {EM} accepted {EM} lost summary",
    ]))
    result = run_script("adr_index", "--write", cwd=root)
    assert result.returncode == 0, result.stderr
    text = (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    assert "0099-gone.md" not in text
    assert "lost summary" in result.stdout        # logged, never silently dropped
    assert "kept" in text


def test_a_malformed_row_is_left_as_written_and_warned(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    write(root / "docs" / "adr" / "README.md", register_with(["- a note with no link"]))
    result = run_script("adr_index", "--write", cwd=root)
    assert result.returncode == 0, result.stderr
    text = (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    assert "- a note with no link" in text
    assert adr_index.UNPARSED_HEADING in text
    assert "unparsed row" in result.stdout


def test_two_rows_with_the_same_href_are_refused(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    write(root / "docs" / "adr" / "README.md", register_with([
        f"- [0007 {EM} A](./0007-order.md) {EM} accepted {EM} one",
        f"- [0007 {EM} B](./0007-order.md) {EM} accepted {EM} two",
    ]))
    for flag in ("--write", "--check"):
        result = run_script("adr_index", flag, cwd=root)
        assert result.returncode == 1
        assert "duplicate" in result.stderr.lower()


# --- Task 13: register injection, --write and --check -----------------------

def test_content_outside_the_markers_is_preserved(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    write(root / "docs" / "adr" / "README.md", register_with([]))
    assert run_script("adr_index", "--write", cwd=root).returncode == 0
    text = (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    assert text.startswith("# Architecture decisions\n\nHand-authored intro.")
    assert text.rstrip().endswith("Hand-authored footer.")
    assert "0007-order.md" in text


def test_a_register_with_no_markers_gets_the_block_appended(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    write(root / "docs" / "adr" / "README.md", "# Architecture decisions\n\nA table.\n")
    assert run_script("adr_index", "--write", cwd=root).returncode == 0
    text = (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    assert text.startswith("# Architecture decisions\n\nA table.")
    assert adr_index.BEGIN in text and adr_index.END in text


def test_a_missing_register_is_created(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    assert run_script("adr_index", "--write", cwd=root).returncode == 0
    assert adr_index.BEGIN in (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8")


def test_check_is_non_zero_when_stale_and_zero_when_fresh(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    assert run_script("adr_index", "--check", cwd=root).returncode == 1   # missing
    run_script("adr_index", "--write", cwd=root)
    assert run_script("adr_index", "--check", cwd=root).returncode == 0
    adr(root, "0008-second.md", area="orders", title="Second")
    stale = run_script("adr_index", "--check", cwd=root)
    assert stale.returncode == 1
    assert "stale" in stale.stdout.lower() + stale.stderr.lower()


def test_check_mutates_nothing(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    before = "# Architecture decisions\n\nno markers here\n"
    write(root / "docs" / "adr" / "README.md", before)
    run_script("adr_index", "--check", cwd=root)
    assert (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8") == before


def test_a_second_write_is_a_no_op(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    run_script("adr_index", "--write", cwd=root)
    first = (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    run_script("adr_index", "--write", cwd=root)
    assert (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8") == first


# --- Task 14: the archived group, so a move is not lossy --------------------

def test_the_register_survives_a_file_moving_into_the_archive(tmp_path):
    root = repo(tmp_path, config={"version": 1, "dir": "docs/adr",
                                  "register": "docs/adr/README.md",
                                  "id_scheme": "sequential", "archive_dir": "archive"})
    adr(root, "0031-retry-backoff.md", area="orders", status="deprecated",
        title="Retry backoff")
    run_script("adr_index", "--write", cwd=root)
    text = (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    text = text.replace("<!-- TODO: summary -->", "Backoff is now the transport's job")
    write(root / "docs" / "adr" / "README.md", text)

    # grooming job 4: move the file, then rewrite the register key to match.
    archive = root / "docs" / "adr" / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    (root / "docs" / "adr" / "0031-retry-backoff.md").rename(archive / "0031-retry-backoff.md")
    text = (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    write(root / "docs" / "adr" / "README.md",
          text.replace("(./0031-retry-backoff.md)", "(./archive/0031-retry-backoff.md)"))

    result = run_script("adr_index", "--write", cwd=root)
    assert result.returncode == 0, result.stderr
    final = (root / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    assert "### archived" in final
    assert "Backoff is now the transport's job" in final
    assert "dropped row" not in result.stdout


def test_the_archived_group_is_absent_when_nothing_is_archived(tmp_path):
    root = repo(tmp_path)
    adr(root, "0007-order.md", area="orders", title="Order state machine")
    assert "### archived" not in adr_index.build_block(adr_lib.load_corpus(root), {})
