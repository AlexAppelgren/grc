"""Adapters and storage (playbook 16, 4.6). The mocks are deterministic, the real
providers are named and refuse to run before their chunk, the factory functions refuse an
unknown provider, and the storage seam refuses the local backend when deployed."""

from __future__ import annotations

import uuid
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.shared import storage
from apps.shared.adapters import agent_runner, embedder, llm, mailer


class LlmAdapter(SimpleTestCase):
    def test_mock_is_deterministic(self) -> None:
        prompt = llm.format_context(["A rule applies."])
        a = llm.get_llm().complete(system="s", prompt=prompt, max_tokens=10)
        b = llm.MockLlm().complete(system="s", prompt=prompt, max_tokens=10)
        self.assertEqual(a, b)
        self.assertEqual(a.model, "mock")

    @override_settings(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="k")
    def test_anthropic_is_the_provider_the_setting_names(self) -> None:
        # What it then does is tests_llm.py's subject, against a stubbed transport.
        self.assertIsInstance(llm.get_llm(), llm.AnthropicLlm)

    @override_settings(LLM_PROVIDER="bedrock")
    def test_bedrock_is_named_but_not_yet_implemented(self) -> None:
        with self.assertRaises(NotImplementedError):
            llm.get_llm().complete(system="s", prompt="p", max_tokens=1)

    @override_settings(LLM_PROVIDER="gpt")
    def test_unknown_provider_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            llm.get_llm()


class EmbedderAdapter(SimpleTestCase):
    @override_settings(EMBEDDING_DIMENSIONS=8)
    def test_mock_yields_unit_vectors_of_the_configured_size(self) -> None:
        vectors = embedder.get_embedder().embed(["a", "b", "a"])
        self.assertEqual(len(vectors), 3)
        self.assertEqual(len(vectors[0]), 8)
        self.assertEqual(vectors[0], vectors[2])
        self.assertNotEqual(vectors[0], vectors[1])
        self.assertAlmostEqual(sum(v * v for v in vectors[0]), 1.0, places=6)

    @override_settings(EMBEDDER_PROVIDER="none")
    def test_none_fails_loudly_on_use(self) -> None:
        adapter = embedder.get_embedder()
        self.assertEqual(adapter.name, "none")
        with self.assertRaises(RuntimeError):
            adapter.embed(["x"])

    @override_settings(EMBEDDER_PROVIDER="voyage")
    def test_unknown_provider_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            embedder.get_embedder()


class AgentRunnerAdapter(SimpleTestCase):
    def test_mock_completes_immediately_and_can_be_interrupted(self) -> None:
        run_id = uuid.uuid4()
        handle = agent_runner.get_agent_runner().start(run_id=run_id, definition_key="watch", definition_version=1)
        self.assertEqual(handle.status, "running")
        self.assertEqual(agent_runner.MockAgentRunner().poll(handle)[-1].status, "succeeded")
        self.assertEqual(agent_runner.MockAgentRunner().interrupt(handle).status, "interrupted")

    @override_settings(AGENT_RUNNER="managed_agents")
    def test_managed_agents_is_named_but_not_yet_implemented(self) -> None:
        with self.assertRaises(NotImplementedError):
            agent_runner.get_agent_runner().start(run_id=uuid.uuid4(), definition_key="w", definition_version=1)

    @override_settings(AGENT_RUNNER="lambda")
    def test_unknown_provider_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            agent_runner.get_agent_runner()


class MailerAdapter(SimpleTestCase):
    def setUp(self) -> None:
        mailer.MockMailer.reset()

    def test_mock_records_what_was_sent(self) -> None:
        mail = mailer.OutgoingMail(to="a@example.invalid", subject="Code", body="123456")
        mailer.get_mailer().send(mail)
        self.assertEqual(mailer.MockMailer.sent, [mail])
        mailer.MockMailer.reset()
        self.assertEqual(mailer.MockMailer.sent, [])

    @override_settings(MAIL_PROVIDER="smtp", MAIL_SMTP_HOST="localhost", MAIL_SMTP_PORT=1)
    def test_smtp_uses_djangos_backend(self) -> None:
        from unittest import mock

        with mock.patch("apps.shared.adapters.mailer.get_connection") as get_connection:
            mailer.get_mailer().send(mailer.OutgoingMail(to="a@example.invalid", subject="s", body="b"))
        self.assertEqual(get_connection.call_args.kwargs["host"], "localhost")
        self.assertTrue(get_connection.call_args.kwargs["use_tls"])

    @override_settings(MAIL_PROVIDER="ses")
    def test_unknown_provider_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            mailer.get_mailer()


class StorageSeam(SimpleTestCase):
    def test_object_keys_are_deterministic_and_never_carry_a_user_path(self) -> None:
        tenant = uuid.uuid4()
        row = uuid.uuid4()
        key = storage.object_key(tenant, row, "../../etc/passwd.PDF")
        self.assertEqual(key, f"{tenant}/{row}.pdf")
        self.assertEqual(storage.object_key(None, row, "x.txt"), f"library/{row}.txt")

    def test_local_backend_round_trips_under_media_root(self) -> None:
        backend = storage.get_storage()
        self.assertIsInstance(backend, storage.LocalStorage)
        key = storage.object_key(None, uuid.uuid4(), "note.txt")
        backend.write(key, b"hello", "text/plain")
        self.assertTrue(backend.exists(key))
        self.assertEqual(backend.read(key), b"hello")
        backend.delete(key)
        self.assertFalse(backend.exists(key))
        with self.assertRaises(ValueError):
            backend.write("../escape.txt", b"x", "text/plain")

    @override_settings(IS_DEPLOYED_ENVIRONMENT=True)
    def test_local_backend_is_refused_when_deployed(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            storage.get_storage()

    @override_settings(STORAGE_BACKEND="s3", STORAGE_S3_BUCKET="")
    def test_s3_needs_a_bucket(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            storage.get_storage()

    @override_settings(STORAGE_BACKEND="s3", STORAGE_S3_BUCKET="evidence", STORAGE_S3_ENDPOINT_URL="https://s3.invalid")
    def test_s3_backend_is_built_from_settings(self) -> None:
        from unittest import mock

        with mock.patch("boto3.client") as client:
            backend = storage.get_storage()
            backend.write("k", b"x", "text/plain")
            client.return_value.exceptions.ClientError = RuntimeError
            client.return_value.head_object.side_effect = RuntimeError("missing")
            self.assertFalse(backend.exists("k"))
            client.return_value.head_object.side_effect = None
            self.assertTrue(backend.exists("k"))
            backend.delete("k")
            client.return_value.get_object.return_value = {"Body": mock.Mock(read=lambda: b"x")}
            self.assertEqual(backend.read("k"), b"x")
        self.assertEqual(client.call_args.kwargs["endpoint_url"], "https://s3.invalid")
        client.return_value.put_object.assert_called_once()

    @override_settings(STORAGE_BACKEND="gcs")
    def test_unknown_backend_is_refused(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            storage.get_storage()

    def test_media_root_is_a_throwaway_directory(self) -> None:
        from django.conf import settings

        self.assertNotIn(str(Path(settings.BASE_DIR)), str(settings.MEDIA_ROOT))
