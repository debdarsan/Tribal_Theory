"""Run: python -m unittest test_core"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from langchain_core.documents import Document

from core.question_generation import (
    PURPOSE_DEMO,
    PURPOSE_GAP_FINDER,
    answer_with_source,
    choose_n_clusters,
    cluster_embeddings,
    delete_all_synthetic_questions,
    generate_and_save_all,
    generate_one_question_for_topic,
    generate_questions_for_topic,
    get_synthetic_question,
    init_questions_db,
    is_topic_in_scope,
    list_synthetic_questions,
    parse_question_response,
    save_answer_and_record_gap,
    save_one_question,
    save_question_answer,
    save_questions,
)
from core.gap_detection import (
    GapMetadata,
    commit_approved_to_validated,
    get_gap,
    init_db,
    is_gap,
    list_pending_reviews,
    parse_metadata_trailer,
    record_gap,
    record_review_decision,
    record_user_input,
)
from core.llm_client import call_llm
from core.rag import (
    Answer,
    Retrieved,
    answer_question,
    compose_messages,
    retrieve,
)


def _non_stream_response(text: str = "hello"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _stream_response(chunks):
    for c in chunks:
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=c))]
        )


class TestCallLLM(unittest.TestCase):
    def test_non_stream_returns_text(self):
        client = Mock()
        client.chat.completions.create.return_value = _non_stream_response("answer")
        result = call_llm(client, [{"role": "user", "content": "q"}], "gpt-4o")
        self.assertEqual(result, "answer")

    def test_stream_yields_chunks(self):
        client = Mock()
        client.chat.completions.create.return_value = _stream_response(["a", "b", "c"])
        result = call_llm(
            client, [{"role": "user", "content": "q"}], "gpt-4o", stream=True
        )
        self.assertEqual("".join(result), "abc")

    def test_gpt5_uses_max_completion_tokens(self):
        client = Mock()
        client.chat.completions.create.return_value = _non_stream_response()
        call_llm(
            client, [{"role": "user", "content": "q"}], "gpt-5.4", max_tokens=500
        )
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs.get("max_completion_tokens"), 500)
        self.assertNotIn("max_tokens", kwargs)

    def test_gpt4_uses_max_tokens(self):
        client = Mock()
        client.chat.completions.create.return_value = _non_stream_response()
        call_llm(
            client, [{"role": "user", "content": "q"}], "gpt-4o", max_tokens=500
        )
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs.get("max_tokens"), 500)
        self.assertNotIn("max_completion_tokens", kwargs)

    def test_retries_then_succeeds(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            RuntimeError("transient 1"),
            RuntimeError("transient 2"),
            _non_stream_response("got it"),
        ]
        result = call_llm(
            client,
            [{"role": "user", "content": "q"}],
            "gpt-4o",
            max_retries=3,
            backoff_seconds=0.0,
        )
        self.assertEqual(result, "got it")
        self.assertEqual(client.chat.completions.create.call_count, 3)

    def test_exhausts_retries_raises(self):
        client = Mock()
        client.chat.completions.create.side_effect = RuntimeError("perma fail")
        with self.assertRaises(RuntimeError) as ctx:
            call_llm(
                client,
                [{"role": "user", "content": "q"}],
                "gpt-4o",
                max_retries=2,
                backoff_seconds=0.0,
            )
        self.assertIn("exhausted 2 retries", str(ctx.exception))


class TestComposeMessages(unittest.TestCase):
    TEMPLATE = (
        "Q: {question}\n"
        "Docs: {source_text}\n"
        "History: {chat_history}\n"
        "Extra: {additional_information}\n"
        "Summary: {content_summary}"
    )

    def test_basic_shape(self):
        messages = compose_messages(
            question="What is X?",
            system_prompt_template=self.TEMPLATE,
            source_text="X is foo.",
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "What is X?")
        self.assertIn("X is foo.", messages[0]["content"])
        self.assertTrue(messages[0]["content"].endswith("\nAnswer:"))

    def test_chat_history_formatted(self):
        messages = compose_messages(
            question="follow up",
            system_prompt_template=self.TEMPLATE,
            source_text="",
            chat_history=[("user", "earlier q"), ("assistant", "earlier a")],
        )
        self.assertIn("User: earlier q", messages[0]["content"])
        self.assertIn("Assistant: earlier a", messages[0]["content"])


class TestRetrieve(unittest.TestCase):
    @patch("core.rag.return_docs_from_vectorstore_parallel")
    def test_text_only_when_no_image_vdb(self, mock_text_retrieve):
        mock_text_retrieve.return_value = ["doc1", "doc2"]
        result = retrieve("q", embeddings=Mock(), vdb=Mock())
        self.assertIsInstance(result, Retrieved)
        self.assertEqual(result.text_docs, ["doc1", "doc2"])
        self.assertEqual(result.image_docs, [])
        mock_text_retrieve.assert_called_once()

    @patch("core.rag.return_docs_from_both_collections_parallel")
    def test_both_collections_when_image_vdb_present(self, mock_both):
        mock_both.return_value = (["t1"], ["i1"])
        result = retrieve("q", embeddings=Mock(), vdb=Mock(), image_vdb=Mock())
        self.assertEqual(result.text_docs, ["t1"])
        self.assertEqual(result.image_docs, ["i1"])
        self.assertEqual(result.all_docs, ["t1", "i1"])


class TestAnswerQuestion(unittest.TestCase):
    TEMPLATE = "{question}|{source_text}|{chat_history}|{additional_information}|{content_summary}"

    @patch("core.rag.return_docs_from_vectorstore_parallel")
    def test_non_stream_returns_answer(self, mock_retrieve):
        mock_retrieve.return_value = [Document(page_content="snippet")]
        client = Mock()
        client.chat.completions.create.return_value = _non_stream_response("final answer")

        result = answer_question(
            "what?",
            client=client,
            model="gpt-4o",
            embeddings=Mock(),
            vdb=Mock(),
            system_prompt_template=self.TEMPLATE,
        )

        self.assertIsInstance(result, Answer)
        self.assertEqual(result.text, "final answer")
        self.assertEqual(result.model, "gpt-4o")
        self.assertEqual(len(result.retrieved.text_docs), 1)

    @patch("core.rag.return_docs_from_vectorstore_parallel")
    def test_answer_question_forwards_validated_vdb_to_retrieve(self, mock_retrieve):
        # Confirm validated_vdb is consumed by answer_question (forwarded to
        # retrieve) and does NOT leak into **llm_kwargs (would blow up call_llm)
        mock_retrieve.return_value = [Document(page_content="manual snippet")]
        client = Mock()
        client.chat.completions.create.return_value = _non_stream_response("ok")

        # Stub validated_vdb whose query returns nothing
        validated_vdb = Mock()
        validated_vdb.similarity_search_with_relevance_scores.return_value = []

        result = answer_question(
            "what is X?",
            client=client, model="gpt-4o",
            embeddings=Mock(), vdb=Mock(),
            system_prompt_template=self.TEMPLATE,
            validated_vdb=validated_vdb,
        )
        self.assertIsInstance(result, Answer)
        # call_llm did not receive validated_vdb as a kwarg
        create_kwargs = client.chat.completions.create.call_args.kwargs
        self.assertNotIn("validated_vdb", create_kwargs)

    @patch("core.rag.return_docs_from_vectorstore_parallel")
    def test_stream_returns_iterator_and_retrieved(self, mock_retrieve):
        mock_retrieve.return_value = [Document(page_content="snippet")]
        client = Mock()
        client.chat.completions.create.return_value = _stream_response(["a", "b"])

        chunks, retrieved = answer_question(
            "what?",
            client=client,
            model="gpt-4o",
            embeddings=Mock(),
            vdb=Mock(),
            system_prompt_template=self.TEMPLATE,
            stream=True,
        )

        self.assertEqual("".join(chunks), "ab")
        self.assertIsInstance(retrieved, Retrieved)


class TestParseMetadataTrailer(unittest.TestCase):
    def test_present_clean(self):
        text = (
            "Here is the answer about BillTrak audits.\n\n"
            "[[META]]\n"
            "CONFIDENCE: 0.82\n"
            "MISSING_INFO: NONE\n"
        )
        cleaned, meta = parse_metadata_trailer(text)
        self.assertEqual(cleaned, "Here is the answer about BillTrak audits.")
        self.assertAlmostEqual(meta.confidence, 0.82)
        self.assertIsNone(meta.missing_info)

    def test_present_with_missing(self):
        text = (
            "Short answer.\n\n"
            "[[META]]\n"
            "CONFIDENCE: 0.3\n"
            "MISSING_INFO: workflow step ordering not described in source\n"
        )
        cleaned, meta = parse_metadata_trailer(text)
        self.assertEqual(cleaned, "Short answer.")
        self.assertAlmostEqual(meta.confidence, 0.3)
        self.assertEqual(meta.missing_info, "workflow step ordering not described in source")

    def test_absent(self):
        text = "Just a plain answer with no metadata trailer."
        cleaned, meta = parse_metadata_trailer(text)
        self.assertEqual(cleaned, text)
        self.assertTrue(meta.is_empty)

    def test_partial_only_confidence(self):
        text = "Answer.\n\n[[META]]\nCONFIDENCE: 0.7\n"
        cleaned, meta = parse_metadata_trailer(text)
        self.assertEqual(cleaned, "Answer.")
        self.assertAlmostEqual(meta.confidence, 0.7)
        self.assertIsNone(meta.missing_info)

    def test_clamps_confidence_to_valid_range(self):
        # The regex only matches 0-1 anyway, but defensive clamping shouldn't change valid values.
        text = "X\n\n[[META]]\nCONFIDENCE: 1.0\nMISSING_INFO: NONE\n"
        _, meta = parse_metadata_trailer(text)
        self.assertEqual(meta.confidence, 1.0)

    def test_uses_last_marker_when_multiple(self):
        text = (
            "First paragraph mentions [[META]] as a literal token.\n\n"
            "Real answer here.\n\n"
            "[[META]]\nCONFIDENCE: 0.5\nMISSING_INFO: NONE\n"
        )
        cleaned, meta = parse_metadata_trailer(text)
        self.assertIn("First paragraph mentions [[META]]", cleaned)
        self.assertIn("Real answer here.", cleaned)
        self.assertAlmostEqual(meta.confidence, 0.5)


class TestIsGap(unittest.TestCase):
    def test_zero_docs_is_gap(self):
        self.assertTrue(is_gap(GapMetadata(confidence=0.9), num_text_docs=0))

    def test_low_confidence_is_gap(self):
        self.assertTrue(is_gap(GapMetadata(confidence=0.3), num_text_docs=5))

    def test_missing_info_is_gap(self):
        self.assertTrue(
            is_gap(GapMetadata(confidence=0.9, missing_info="something"), num_text_docs=5)
        )

    def test_high_confidence_no_missing_is_not_gap(self):
        self.assertFalse(is_gap(GapMetadata(confidence=0.9), num_text_docs=5))

    def test_no_metadata_with_docs_is_not_gap(self):
        # If LLM forgot the trailer entirely AND docs were retrieved, treat as non-gap.
        self.assertFalse(is_gap(GapMetadata(), num_text_docs=5))


class TestRecordGap(unittest.TestCase):
    def setUp(self):
        import shutil
        self._shutil = shutil
        self.tmpdir = tempfile.mkdtemp(prefix="gaps_test_")
        self.db_path = Path(self.tmpdir) / "gaps.db"

    def tearDown(self):
        # ignore_errors handles Windows holding a sqlite file lock briefly
        self._shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_creates_table(self):
        init_db(self.db_path)
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='gaps'"
            ).fetchone()
            self.assertEqual(row[0], "gaps")

    def test_record_inserts_with_gap_flag(self):
        rowid = record_gap(
            self.db_path,
            question="how do I X?",
            answer="here's how",
            metadata=GapMetadata(confidence=0.3, missing_info="step 2 unclear"),
            num_text_docs=2,
            num_image_docs=0,
            user_name="testuser",
            model="gpt-4o",
        )
        self.assertGreater(rowid, 0)

        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT question, confidence, missing_info, is_gap, user_name, model FROM gaps WHERE id=?",
                (rowid,),
            ).fetchone()
        self.assertEqual(row[0], "how do I X?")
        self.assertAlmostEqual(row[1], 0.3)
        self.assertEqual(row[2], "step 2 unclear")
        self.assertEqual(row[3], 1)
        self.assertEqual(row[4], "testuser")
        self.assertEqual(row[5], "gpt-4o")

    def test_record_high_confidence_not_flagged(self):
        rowid = record_gap(
            self.db_path,
            question="trivial",
            answer="A",
            metadata=GapMetadata(confidence=0.9),
            num_text_docs=3,
        )
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute("SELECT is_gap FROM gaps WHERE id=?", (rowid,)).fetchone()
        self.assertEqual(row[0], 0)


class TestUserInput(unittest.TestCase):
    def setUp(self):
        import shutil
        self._shutil = shutil
        self.tmpdir = tempfile.mkdtemp(prefix="gaps_userinput_")
        self.db_path = Path(self.tmpdir) / "gaps.db"
        self.gap_id = record_gap(
            self.db_path,
            question="how do I X?",
            answer="not in docs",
            metadata=GapMetadata(confidence=0.2, missing_info="X is not covered"),
            num_text_docs=0,
            user_name="asker",
            model="gpt-4o",
        )

    def tearDown(self):
        self._shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_record_user_input_writes_columns(self):
        ok = record_user_input(
            self.db_path, self.gap_id, "I know X works like Y", user_name="contributor"
        )
        self.assertTrue(ok)
        row = get_gap(self.db_path, self.gap_id)
        self.assertEqual(row["user_input"], "I know X works like Y")
        self.assertEqual(row["user_input_by"], "contributor")
        self.assertIsNotNone(row["user_input_at"])

    def test_record_user_input_returns_false_for_unknown_id(self):
        ok = record_user_input(self.db_path, 99999, "ignored")
        self.assertFalse(ok)

    def test_get_gap_unknown_returns_none(self):
        self.assertIsNone(get_gap(self.db_path, 99999))


class TestReviewWorkflow(unittest.TestCase):
    def setUp(self):
        import shutil
        self._shutil = shutil
        self.tmpdir = tempfile.mkdtemp(prefix="gaps_review_")
        self.db_path = Path(self.tmpdir) / "gaps.db"
        # Two gaps: one with user input (pending), one without (not yet input)
        self.pending_id = record_gap(
            self.db_path,
            question="how do I X?", answer="no idea",
            metadata=GapMetadata(confidence=0.2, missing_info="X unclear"),
            num_text_docs=0, user_name="asker",
        )
        record_user_input(self.db_path, self.pending_id, "X works via Y", user_name="contrib")
        self.no_input_id = record_gap(
            self.db_path,
            question="another gap", answer="dunno",
            metadata=GapMetadata(confidence=0.3),
            num_text_docs=0, user_name="asker2",
        )

    def tearDown(self):
        self._shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_list_pending_shows_only_user_input_undecided(self):
        pending = list_pending_reviews(self.db_path)
        ids = {r["id"] for r in pending}
        self.assertIn(self.pending_id, ids)
        self.assertNotIn(self.no_input_id, ids)

    def test_approve_marks_row_and_removes_from_pending(self):
        ok = record_review_decision(
            self.db_path, self.pending_id, "approved",
            reviewer_name="senior", comment="looks right",
        )
        self.assertTrue(ok)
        row = get_gap(self.db_path, self.pending_id)
        self.assertEqual(row["reviewer_decision"], "approved")
        self.assertEqual(row["reviewer_name"], "senior")
        self.assertEqual(row["reviewer_comment"], "looks right")
        self.assertIsNotNone(row["reviewed_at"])
        # Pending list no longer includes it
        self.assertNotIn(self.pending_id, {r["id"] for r in list_pending_reviews(self.db_path)})

    def test_approve_with_edit_preserves_original(self):
        record_review_decision(
            self.db_path, self.pending_id, "approved",
            reviewer_name="senior",
            edited_text="X works via Y (and also via Z)",
        )
        row = get_gap(self.db_path, self.pending_id)
        self.assertEqual(row["user_input"], "X works via Y")  # original unchanged
        self.assertEqual(row["reviewer_edited_text"], "X works via Y (and also via Z)")

    def test_reject(self):
        ok = record_review_decision(
            self.db_path, self.pending_id, "rejected",
            reviewer_name="senior", comment="incorrect",
        )
        self.assertTrue(ok)
        row = get_gap(self.db_path, self.pending_id)
        self.assertEqual(row["reviewer_decision"], "rejected")

    def test_invalid_decision_raises(self):
        with self.assertRaises(ValueError):
            record_review_decision(self.db_path, self.pending_id, "maybe", reviewer_name="x")


class TestCommitToValidated(unittest.TestCase):
    """Validation-only tests for commit_approved_to_validated. The Chroma
    write path is exercised by the live app and isn't easy to unit-test
    on Windows without the file-lock + binary issues we hit earlier."""

    def setUp(self):
        import shutil
        self._shutil = shutil
        self.tmpdir = tempfile.mkdtemp(prefix="gaps_commit_")
        self.db_path = Path(self.tmpdir) / "gaps.db"
        self.fake_chroma_dir = Path(self.tmpdir) / "fake_chroma"

    def tearDown(self):
        self._shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_gap(self, *, with_input=True, decision=None, edited=None):
        gid = record_gap(
            self.db_path,
            question="how does X work?", answer="dunno",
            metadata=GapMetadata(confidence=0.2, missing_info="X not covered"),
            num_text_docs=0,
        )
        if with_input:
            record_user_input(self.db_path, gid, "X works via Y", user_name="user1")
        if decision:
            record_review_decision(
                self.db_path, gid, decision,
                reviewer_name="reviewer", edited_text=edited,
            )
        return gid

    def test_unknown_gap_raises(self):
        with self.assertRaises(ValueError) as ctx:
            commit_approved_to_validated(
                chroma_dir=self.fake_chroma_dir, embeddings=Mock(),
                db_path=self.db_path, gap_id=99999,
            )
        self.assertIn("not found", str(ctx.exception))

    def test_unreviewed_gap_raises(self):
        gid = self._make_gap(with_input=True, decision=None)
        with self.assertRaises(ValueError) as ctx:
            commit_approved_to_validated(
                chroma_dir=self.fake_chroma_dir, embeddings=Mock(),
                db_path=self.db_path, gap_id=gid,
            )
        self.assertIn("not approved", str(ctx.exception))

    def test_rejected_gap_raises(self):
        gid = self._make_gap(with_input=True, decision="rejected")
        with self.assertRaises(ValueError) as ctx:
            commit_approved_to_validated(
                chroma_dir=self.fake_chroma_dir, embeddings=Mock(),
                db_path=self.db_path, gap_id=gid,
            )
        self.assertIn("not approved", str(ctx.exception))


class TestSchemaMigration(unittest.TestCase):
    def setUp(self):
        import shutil
        self._shutil = shutil
        self.tmpdir = tempfile.mkdtemp(prefix="gaps_migration_")
        self.db_path = Path(self.tmpdir) / "gaps.db"

    def tearDown(self):
        self._shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_migration_adds_columns_to_old_schema(self):
        # Simulate the pre-migration schema (no user_input columns)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE gaps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_name TEXT,
                    model TEXT,
                    question TEXT NOT NULL,
                    answer TEXT,
                    confidence REAL,
                    missing_info TEXT,
                    num_text_docs INTEGER,
                    num_image_docs INTEGER,
                    is_gap INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO gaps (timestamp, question, is_gap) VALUES (?, ?, ?)",
                ("2026-05-17T00:00:00", "pre-migration row", 1),
            )

        init_db(self.db_path)

        with sqlite3.connect(str(self.db_path)) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(gaps)")}
        for c in ("user_input", "user_input_at", "user_input_by"):
            self.assertIn(c, cols)

        ok = record_user_input(self.db_path, 1, "added after migration", user_name="me")
        self.assertTrue(ok)
        row = get_gap(self.db_path, 1)
        self.assertEqual(row["user_input"], "added after migration")


class TestParseQuestionResponse(unittest.TestCase):
    def test_clean_json(self):
        text = '[{"type": "factoid", "text": "What is X?"}, {"type": "conceptual", "text": "Why X?"}]'
        items = parse_question_response(text)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["type"], "factoid")
        self.assertEqual(items[1]["text"], "Why X?")

    def test_json_with_surrounding_prose(self):
        text = 'Here you go:\n[{"type": "factoid", "text": "Q1"}]\nHope this helps!'
        items = parse_question_response(text)
        self.assertEqual(len(items), 1)

    def test_json_with_markdown_fence(self):
        text = '```json\n[{"type": "edge_case", "text": "Q1"}]\n```'
        items = parse_question_response(text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "edge_case")

    def test_type_normalization(self):
        text = '[{"type": "Edge Case", "text": "Q1"}, {"type": "edge-case", "text": "Q2"}]'
        items = parse_question_response(text)
        self.assertEqual(items[0]["type"], "edge_case")
        self.assertEqual(items[1]["type"], "edge_case")

    def test_unknown_type_defaults_to_factoid(self):
        text = '[{"type": "trivia", "text": "Q"}]'
        items = parse_question_response(text)
        self.assertEqual(items[0]["type"], "factoid")

    def test_empty_text_skipped(self):
        text = '[{"type": "factoid", "text": ""}, {"type": "conceptual", "text": "Q"}]'
        items = parse_question_response(text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "Q")

    def test_invalid_inputs(self):
        for bad in ("", "not json", "{}", "[]"):
            self.assertEqual(parse_question_response(bad), [])


class TestChooseNClusters(unittest.TestCase):
    def test_zero_or_one_chunk(self):
        self.assertEqual(choose_n_clusters(0), 1)
        self.assertEqual(choose_n_clusters(1), 1)

    def test_small_chunks_hits_min_k(self):
        # 4 chunks: 4//5=0 → max(min_k=2, 0) = 2, clamped to n=4 → 2
        self.assertEqual(choose_n_clusters(4), 2)

    def test_medium_chunks(self):
        # 25 chunks: 25//5=5, clamp to [2,12] → 5
        self.assertEqual(choose_n_clusters(25), 5)

    def test_large_chunks_hits_max_k(self):
        # 200 chunks: 200//5=40, clamp to max_k=12 → 12
        self.assertEqual(choose_n_clusters(200), 12)


class TestSyntheticAnswerCache(unittest.TestCase):
    def setUp(self):
        import shutil
        self._shutil = shutil
        self.tmpdir = tempfile.mkdtemp(prefix="synq_ans_")
        self.db_path = Path(self.tmpdir) / "qs.db"
        save_questions(self.db_path, 0, [{"type": "factoid", "text": "What is X?"}], ["c1"])
        self.qid = list_synthetic_questions(self.db_path)[0]["id"]

    def tearDown(self):
        self._shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_question_answer_populates_columns(self):
        ok = save_question_answer(self.db_path, self.qid, "X is foo", 0.85, None)
        self.assertTrue(ok)
        row = get_synthetic_question(self.db_path, self.qid)
        self.assertEqual(row["answer_text"], "X is foo")
        self.assertAlmostEqual(row["answer_confidence"], 0.85)
        self.assertIsNone(row["answer_missing_info"])
        self.assertEqual(row["status"], "answered")
        self.assertIsNotNone(row["answered_at"])

    def test_save_question_answer_unknown_id_returns_false(self):
        self.assertFalse(save_question_answer(self.db_path, 99999, "x", 0.5, None))

    def test_schema_migration_on_old_table(self):
        # Drop the cache columns to simulate a pre-migration schema, then
        # re-init and verify the columns reappear.
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """CREATE TABLE _tmp AS SELECT id, cluster_id, question_type, text,
                                              generated_at, source_chunk_ids, status
                   FROM synthetic_questions"""
            )
            conn.execute("DROP TABLE synthetic_questions")
            conn.execute("ALTER TABLE _tmp RENAME TO synthetic_questions")
        init_questions_db(self.db_path)
        with sqlite3.connect(str(self.db_path)) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(synthetic_questions)")}
        for c in ("answer_text", "answer_confidence", "answer_missing_info", "answered_at"):
            self.assertIn(c, cols)


class TestTopicScope(unittest.TestCase):
    def _make_vdb(self, scored_docs):
        vdb = Mock()
        vdb.similarity_search_with_relevance_scores.return_value = scored_docs
        return vdb

    def test_empty_topic_out_of_scope(self):
        in_scope, score, docs = is_topic_in_scope("", self._make_vdb([]))
        self.assertFalse(in_scope)
        self.assertEqual(score, 0.0)
        self.assertEqual(docs, [])

    def test_no_results_out_of_scope(self):
        in_scope, score, docs = is_topic_in_scope("weather", self._make_vdb([]))
        self.assertFalse(in_scope)

    def test_below_threshold_out_of_scope(self):
        d = Document(page_content="text")
        in_scope, score, docs = is_topic_in_scope(
            "sports", self._make_vdb([(d, 0.15)]), relevance_threshold=0.3
        )
        self.assertFalse(in_scope)
        self.assertAlmostEqual(score, 0.15)

    def test_above_threshold_in_scope(self):
        d = Document(page_content="text")
        in_scope, score, docs = is_topic_in_scope(
            "workflow", self._make_vdb([(d, 0.45)]), relevance_threshold=0.3
        )
        self.assertTrue(in_scope)
        self.assertAlmostEqual(score, 0.45)
        self.assertEqual(len(docs), 1)

    def test_vdb_exception_out_of_scope(self):
        vdb = Mock()
        vdb.similarity_search_with_relevance_scores.side_effect = RuntimeError("boom")
        in_scope, score, docs = is_topic_in_scope("anything", vdb)
        self.assertFalse(in_scope)


class TestGenerateQuestionsForTopic(unittest.TestCase):
    def setUp(self):
        import shutil
        self._shutil = shutil
        self.tmpdir = tempfile.mkdtemp(prefix="synq_topic_")
        self.db_path = Path(self.tmpdir) / "qs.db"

    def tearDown(self):
        self._shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_topic_returns_reason(self):
        result = generate_questions_for_topic(
            client=Mock(), model="gpt-4o", vdb=Mock(), db_path=self.db_path, topic="",
        )
        self.assertFalse(result["in_scope"])
        self.assertEqual(result["n_questions"], 0)
        self.assertIn("topic", result["reason"].lower())

    def test_out_of_scope_topic(self):
        vdb = Mock()
        vdb.similarity_search_with_relevance_scores.return_value = [
            (Document(page_content="unrelated"), 0.1),
        ]
        result = generate_questions_for_topic(
            client=Mock(), model="gpt-4o", vdb=vdb, db_path=self.db_path,
            topic="weather forecast",
        )
        self.assertFalse(result["in_scope"])
        self.assertEqual(result["n_questions"], 0)
        self.assertIn("BillTrak", result["reason"])

    def test_in_scope_topic_saves_questions(self):
        # vdb returns a relevant chunk with score above threshold
        relevant_doc = Document(
            page_content="Workflow is the component of BillTrak…",
            metadata={"File": "Workflow Best Practices", "Section": "Intro", "Split": 1},
        )
        vdb = Mock()
        vdb.similarity_search_with_relevance_scores.return_value = [(relevant_doc, 0.62)]

        # Stub the LLM to return parseable JSON
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content='[{"type": "factoid", "text": "What is workflow?"}, {"type": "conceptual", "text": "Why does workflow matter?"}]'
            ))]
        )
        result = generate_questions_for_topic(
            client=client, model="gpt-4o", vdb=vdb, db_path=self.db_path,
            topic="workflow", per_type=1,
        )
        self.assertTrue(result["in_scope"])
        self.assertEqual(result["n_questions"], 2)
        rows = list_synthetic_questions(self.db_path)
        self.assertEqual(len(rows), 2)
        # topic column should be set
        self.assertEqual(rows[0]["topic"], "workflow")
        # cluster_id should be -1 for topic-based generation
        self.assertEqual(rows[0]["cluster_id"], -1)


class TestGenerateOneQuestion(unittest.TestCase):
    def setUp(self):
        import shutil
        self._shutil = shutil
        self.tmpdir = tempfile.mkdtemp(prefix="synq_one_")
        self.db_path = Path(self.tmpdir) / "qs.db"

    def tearDown(self):
        self._shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _llm_returning(self, text):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        )
        return client

    def test_out_of_scope_topic_returns_no_question(self):
        vdb = Mock()
        vdb.similarity_search_with_relevance_scores.return_value = [
            (Document(page_content="unrelated"), 0.1),
        ]
        result = generate_one_question_for_topic(
            client=self._llm_returning("ignored"), model="gpt-4o", vdb=vdb,
            db_path=self.db_path, topic="weather forecast",
        )
        self.assertFalse(result["in_scope"])
        self.assertIsNone(result["question_id"])

    def test_in_scope_topic_generates_one_question(self):
        relevant = Document(
            page_content="Workflow processes invoices",
            metadata={"File": "Workflow", "Split": 1},
        )
        vdb = Mock()
        vdb.similarity_search_with_relevance_scores.return_value = [(relevant, 0.7)]
        client = self._llm_returning(
            '[{"type": "factoid", "text": "What does workflow do?"}]'
        )
        result = generate_one_question_for_topic(
            client=client, model="gpt-4o", vdb=vdb,
            db_path=self.db_path, topic="workflow",
        )
        self.assertTrue(result["in_scope"])
        self.assertIsNotNone(result["question_id"])
        self.assertEqual(result["question_type"], "factoid")
        self.assertEqual(result["question_text"], "What does workflow do?")
        # Verify the row exists in DB with topic set
        rows = list_synthetic_questions(self.db_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["topic"], "workflow")
        self.assertEqual(rows[0]["cluster_id"], -1)

    def test_no_topic_samples_from_corpus(self):
        # No topic → don't call similarity_search; instead use extract_chunks
        vdb = Mock()
        vdb._collection.get.return_value = {
            "ids": ["c1", "c2", "c3"],
            "embeddings": [[0.1]*3, [0.2]*3, [0.3]*3],
            "documents": ["doc one content", "doc two content", "doc three content"],
            "metadatas": [{"File": "A"}, {"File": "B"}, {"File": "C"}],
        }
        client = self._llm_returning(
            '[{"type": "edge_case", "text": "What if X?"}]'
        )
        result = generate_one_question_for_topic(
            client=client, model="gpt-4o", vdb=vdb,
            db_path=self.db_path, topic="",
        )
        self.assertTrue(result["in_scope"])
        self.assertIsNotNone(result["question_id"])
        # similarity_search should NOT have been called when topic is blank
        vdb.similarity_search_with_relevance_scores.assert_not_called()
        # extract_chunks SHOULD have been called
        vdb._collection.get.assert_called_once()
        # Topic column is NULL/empty when no topic given
        rows = list_synthetic_questions(self.db_path)
        self.assertIsNone(rows[0]["topic"])

    def test_no_topic_empty_corpus_returns_reason(self):
        vdb = Mock()
        vdb._collection.get.return_value = {
            "ids": [], "embeddings": [], "documents": [], "metadatas": []
        }
        result = generate_one_question_for_topic(
            client=Mock(), model="gpt-4o", vdb=vdb,
            db_path=self.db_path, topic="",
        )
        self.assertFalse(result["in_scope"])
        self.assertIn("empty", result["reason"].lower())

    def test_save_one_question_returns_rowid(self):
        qid = save_one_question(
            self.db_path, cluster_id=-1,
            item={"type": "factoid", "text": "Q?"},
            source_chunk_ids=["c1"],
            topic="my topic",
        )
        self.assertGreater(qid, 0)
        row = get_synthetic_question(self.db_path, qid)
        self.assertEqual(row["text"], "Q?")
        self.assertEqual(row["topic"], "my topic")
        # Default purpose is 'demo'
        self.assertEqual(row["purpose"], PURPOSE_DEMO)

    def test_purpose_persisted_when_specified(self):
        qid = save_one_question(
            self.db_path, cluster_id=-1,
            item={"type": "edge_case", "text": "Edge?"},
            source_chunk_ids=["c1"],
            topic="boundaries",
            purpose=PURPOSE_GAP_FINDER,
        )
        row = get_synthetic_question(self.db_path, qid)
        self.assertEqual(row["purpose"], PURPOSE_GAP_FINDER)

    def test_demo_purpose_no_topic_uses_single_chunk(self):
        vdb = Mock()
        vdb._collection.get.return_value = {
            "ids": ["c1", "c2", "c3"],
            "embeddings": [[0.1]*3, [0.2]*3, [0.3]*3],
            "documents": ["doc one", "doc two", "doc three"],
            "metadatas": [{}, {}, {}],
        }
        client = self._llm_returning('[{"type": "factoid", "text": "Q?"}]')
        result = generate_one_question_for_topic(
            client=client, model="gpt-4o", vdb=vdb,
            db_path=self.db_path, topic="", purpose=PURPOSE_DEMO,
        )
        self.assertTrue(result["in_scope"])
        # Source chunk content is returned so the UI can answer from it directly
        self.assertIsNotNone(result["source_chunk_content"])
        self.assertIn(result["source_chunk_content"], ("doc one", "doc two", "doc three"))

    def test_gap_finder_purpose_no_topic_uses_multiple_chunks(self):
        vdb = Mock()
        vdb._collection.get.return_value = {
            "ids": ["c1", "c2", "c3"],
            "embeddings": [[0.1]*3, [0.2]*3, [0.3]*3],
            "documents": ["doc one", "doc two", "doc three"],
            "metadatas": [{}, {}, {}],
        }
        client = self._llm_returning('[{"type": "edge_case", "text": "Q?"}]')
        result = generate_one_question_for_topic(
            client=client, model="gpt-4o", vdb=vdb,
            db_path=self.db_path, topic="", purpose=PURPOSE_GAP_FINDER,
        )
        self.assertTrue(result["in_scope"])
        # Gap finder doesn't return single-chunk content (uses multi-chunk retrieval)
        self.assertIsNone(result["source_chunk_content"])

    def test_answer_with_source_bypasses_retrieval(self):
        # Stub LLM to return a plain answer with no metadata trailer
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content="The answer is X."
            ))]
        )
        ar = answer_with_source(
            client=client, model="gpt-4o",
            question_text="What is X?",
            source_text="X is foo.",
            system_prompt_template="Q: {question}\nDocs: {source_text}\nHist: {chat_history}\nExtra: {additional_information}\nSummary: {content_summary}",
        )
        self.assertEqual(ar["answer"], "The answer is X.")
        self.assertEqual(ar["num_text_docs"], 1)
        self.assertEqual(ar["num_image_docs"], 0)

    def test_gap_finder_purpose_propagates_through_generate(self):
        relevant = Document(page_content="X has boundary Y", metadata={"File": "F", "Split": 1})
        vdb = Mock()
        vdb.similarity_search_with_relevance_scores.return_value = [(relevant, 0.7)]
        client = self._llm_returning('[{"type": "edge_case", "text": "What if Z?"}]')
        result = generate_one_question_for_topic(
            client=client, model="gpt-4o", vdb=vdb,
            db_path=self.db_path, topic="boundaries",
            purpose=PURPOSE_GAP_FINDER,
        )
        self.assertEqual(result["purpose"], PURPOSE_GAP_FINDER)
        row = get_synthetic_question(self.db_path, result["question_id"])
        self.assertEqual(row["purpose"], PURPOSE_GAP_FINDER)


class TestSaveAnswerAndRecordGap(unittest.TestCase):
    def setUp(self):
        import shutil
        self._shutil = shutil
        self.tmpdir = tempfile.mkdtemp(prefix="synq_gap_")
        self.db_path = Path(self.tmpdir) / "qs.db"
        save_questions(self.db_path, 0, [{"type": "factoid", "text": "What is X?"}], ["c1"])
        self.qid = list_synthetic_questions(self.db_path)[0]["id"]

    def tearDown(self):
        self._shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_records_gap_when_low_confidence(self):
        gid = save_answer_and_record_gap(
            self.db_path, self.qid,
            answer="not sure", confidence=0.3, missing_info="X not covered",
            num_text_docs=2, num_image_docs=0,
            user_name="testuser", model="gpt-4o",
        )
        self.assertIsNotNone(gid)
        synth = get_synthetic_question(self.db_path, self.qid)
        self.assertEqual(synth["gap_id"], gid)
        # Verify the corresponding gap row exists
        from core.gap_detection import get_gap
        gap = get_gap(self.db_path, gid)
        self.assertEqual(gap["question"], "What is X?")
        self.assertEqual(gap["is_gap"], 1)

    def test_no_gap_when_high_confidence(self):
        gid = save_answer_and_record_gap(
            self.db_path, self.qid,
            answer="X is foo", confidence=0.95, missing_info=None,
            num_text_docs=5, num_image_docs=0,
        )
        self.assertIsNone(gid)
        synth = get_synthetic_question(self.db_path, self.qid)
        self.assertIsNone(synth["gap_id"])

    def test_idempotent_on_re_call(self):
        gid1 = save_answer_and_record_gap(
            self.db_path, self.qid,
            answer="not sure", confidence=0.3, missing_info="X not covered",
            num_text_docs=0,
        )
        gid2 = save_answer_and_record_gap(
            self.db_path, self.qid,
            answer="still not sure", confidence=0.2, missing_info="still missing",
            num_text_docs=0,
        )
        # Same gap_id returned the second time — no duplicate gap row
        self.assertEqual(gid1, gid2)
        with sqlite3.connect(str(self.db_path)) as conn:
            n_gaps = conn.execute("SELECT COUNT(*) FROM gaps").fetchone()[0]
        self.assertEqual(n_gaps, 1)


class TestClusterClamp(unittest.TestCase):
    def test_explicit_n_clusters_clamped_to_chunk_count(self):
        # 2-chunk fake vdb, user requests 5 clusters — must clamp to 2 and not error
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="synq_clamp_")
        try:
            db_path = Path(tmpdir) / "qs.db"
            fake_vdb = Mock()
            fake_vdb._collection.get.return_value = {
                "ids": ["c1", "c2"],
                "embeddings": [[0.1, 0.2, 0.3], [0.9, 0.8, 0.7]],
                "documents": ["doc one", "doc two"],
                "metadatas": [{}, {}],
            }
            # call_llm gets patched at the module where generate_questions_for_cluster looks it up
            with patch("core.question_generation.generate_questions_for_cluster",
                       return_value=[{"type": "factoid", "text": "Q?"}]):
                summary = generate_and_save_all(
                    client=Mock(), model="gpt-4o", vdb=fake_vdb,
                    db_path=db_path, n_clusters=5, per_type=1,
                )
            self.assertEqual(summary.n_chunks, 2)
            self.assertEqual(summary.n_clusters, 2)
            self.assertGreaterEqual(summary.n_questions, 1)
            self.assertEqual(summary.errors, [])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestSyntheticQuestionsDB(unittest.TestCase):
    def setUp(self):
        import shutil
        self._shutil = shutil
        self.tmpdir = tempfile.mkdtemp(prefix="synq_")
        self.db_path = Path(self.tmpdir) / "qs.db"

    def tearDown(self):
        self._shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_creates_table(self):
        init_questions_db(self.db_path)
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='synthetic_questions'"
            ).fetchone()
            self.assertEqual(row[0], "synthetic_questions")

    def test_save_and_list(self):
        items = [
            {"type": "factoid", "text": "What is X?"},
            {"type": "conceptual", "text": "Why does X work?"},
        ]
        n = save_questions(self.db_path, cluster_id=2, items=items, source_chunk_ids=["c1", "c2"])
        self.assertEqual(n, 2)
        out = list_synthetic_questions(self.db_path)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["cluster_id"], 2)
        self.assertIn(out[0]["question_type"], ("factoid", "conceptual"))
        self.assertEqual(out[0]["status"], "pending")

    def test_filter_by_status(self):
        save_questions(self.db_path, 0, [{"type": "factoid", "text": "Q"}], ["c1"])
        self.assertEqual(len(list_synthetic_questions(self.db_path, status="pending")), 1)
        self.assertEqual(len(list_synthetic_questions(self.db_path, status="processed")), 0)

    def test_delete_all(self):
        save_questions(self.db_path, 0, [{"type": "factoid", "text": "Q"}], ["c1"])
        self.assertEqual(delete_all_synthetic_questions(self.db_path), 1)
        self.assertEqual(len(list_synthetic_questions(self.db_path)), 0)


if __name__ == "__main__":
    unittest.main()
