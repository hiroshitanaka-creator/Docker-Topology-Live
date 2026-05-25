"""Tests for Docker API-side event filtering (Goal 10).

All tests run without a real Docker daemon.

Coverage:
- docker_event_filters() returns deterministic, correct filters
- _subscribe_event_stream() uses filters and falls back on failure
- stream_live() passes filters to client.events()
- Python-side is_relevant_event() is still applied after API filtering
- Fallback path works without traceback leakage
"""
import io
import json
import logging
import sys
import unittest
from unittest.mock import MagicMock, call, patch

from docker_topology_live.events import (
    SSEWriter,
    _RELEVANT_ACTIONS,
    _RELEVANT_TYPES,
    _subscribe_event_stream,
    docker_event_filters,
    is_relevant_event,
    stream_live,
)


# ── docker_event_filters() ────────────────────────────────────────────────────

class TestDockerEventFilters(unittest.TestCase):
    """docker_event_filters() must return a deterministic, correct filter dict."""

    def setUp(self):
        self.filters = docker_event_filters()

    def test_returns_dict(self):
        self.assertIsInstance(self.filters, dict)

    def test_deterministic(self):
        """Calling twice must return the same value."""
        a = docker_event_filters()
        b = docker_event_filters()
        self.assertEqual(a, b)

    def test_has_type_key(self):
        self.assertIn("type", self.filters,
                      "filters must have a 'type' key for Docker event type filtering")

    def test_has_event_key(self):
        self.assertIn("event", self.filters,
                      "filters must have an 'event' key for Docker event action filtering")

    def test_type_contains_container(self):
        self.assertIn("container", self.filters["type"],
                      "filters['type'] must include 'container'")

    def test_type_contains_network(self):
        self.assertIn("network", self.filters["type"],
                      "filters['type'] must include 'network'")

    def test_type_only_container_and_network(self):
        """Only container and network types should be requested."""
        self.assertEqual(
            set(self.filters["type"]),
            {"container", "network"},
            "filters['type'] must contain exactly 'container' and 'network'",
        )

    def test_event_contains_lifecycle_actions(self):
        """Core container lifecycle actions must be included."""
        for action in ("create", "start", "stop", "die", "destroy"):
            with self.subTest(action=action):
                self.assertIn(action, self.filters["event"],
                              f"filters['event'] must include '{action}'")

    def test_event_contains_network_membership_actions(self):
        """Network membership actions must be included."""
        self.assertIn("connect", self.filters["event"])
        self.assertIn("disconnect", self.filters["event"])

    def test_event_contains_all_relevant_actions(self):
        """Every action in _RELEVANT_ACTIONS must appear in the filters."""
        for action in _RELEVANT_ACTIONS:
            with self.subTest(action=action):
                self.assertIn(action, self.filters["event"],
                              f"_RELEVANT_ACTIONS action '{action}' missing from filters")

    def test_type_list_is_sorted(self):
        """Sorted order aids determinism and log readability."""
        self.assertEqual(self.filters["type"], sorted(self.filters["type"]))

    def test_event_list_is_sorted(self):
        self.assertEqual(self.filters["event"], sorted(self.filters["event"]))

    def test_filters_types_are_lists(self):
        """docker-py expects list values for filter keys."""
        self.assertIsInstance(self.filters["type"],  list)
        self.assertIsInstance(self.filters["event"], list)

    def test_filters_consistent_with_relevant_types(self):
        """Filter types must match _RELEVANT_TYPES exactly."""
        self.assertEqual(set(self.filters["type"]), _RELEVANT_TYPES)

    def test_filters_consistent_with_relevant_actions(self):
        """Filter events must match _RELEVANT_ACTIONS exactly."""
        self.assertEqual(set(self.filters["event"]), _RELEVANT_ACTIONS)


# ── _subscribe_event_stream() ─────────────────────────────────────────────────

class TestSubscribeEventStream(unittest.TestCase):
    """_subscribe_event_stream() must use filters and fall back safely."""

    def _make_client(self, side_effect=None, return_value=None):
        client = MagicMock()
        if side_effect is not None:
            client.events.side_effect = side_effect
        else:
            client.events.return_value = iter(return_value or [])
        return client

    def test_calls_events_with_filters_by_default(self):
        """Must call client.events() with filters= when no error occurs."""
        client = self._make_client(return_value=[])
        _subscribe_event_stream(client)
        call_kwargs = client.events.call_args_list[0][1]
        self.assertIn("filters", call_kwargs,
                      "_subscribe_event_stream must pass filters= to client.events()")

    def test_filters_passed_match_docker_event_filters(self):
        """The filters passed must equal docker_event_filters()."""
        client = self._make_client(return_value=[])
        _subscribe_event_stream(client)
        call_kwargs = client.events.call_args_list[0][1]
        self.assertEqual(call_kwargs["filters"], docker_event_filters())

    def test_decode_true_passed_in_filtered_call(self):
        """decode=True must be set regardless of filter path."""
        client = self._make_client(return_value=[])
        _subscribe_event_stream(client)
        call_kwargs = client.events.call_args_list[0][1]
        self.assertTrue(call_kwargs.get("decode"),
                        "decode=True must be passed to client.events()")

    def test_returns_stream_on_success(self):
        """Must return the stream object from client.events()."""
        expected = iter([{"Type": "container", "Action": "start"}])
        client = self._make_client(return_value=list(expected))
        result = _subscribe_event_stream(client)
        self.assertIsNotNone(result)

    def test_fallback_on_filter_error(self):
        """If filtered call raises, must fall back to unfiltered call."""
        call_count = [0]
        fallback_stream = iter([])

        def _side_effect(*args, **kwargs):
            call_count[0] += 1
            if kwargs.get("filters") is not None:
                raise Exception("filter not supported")
            return fallback_stream

        client = MagicMock()
        client.events.side_effect = _side_effect

        result = _subscribe_event_stream(client)

        # Must have been called twice: once filtered (raises), once unfiltered
        self.assertEqual(call_count[0], 2,
                         "Must attempt filtered call then fallback unfiltered call")
        # Second call must not have filters=
        second_kwargs = client.events.call_args_list[1][1]
        self.assertNotIn("filters", second_kwargs,
                         "Fallback call must not pass filters=")

    def test_fallback_returns_unfiltered_stream(self):
        """Fallback must return a usable stream from the unfiltered call."""
        fallback_events = [{"Type": "container", "Action": "create"}]

        def _side_effect(*args, **kwargs):
            if kwargs.get("filters") is not None:
                raise TypeError("filters not supported by this SDK version")
            return iter(fallback_events)

        client = MagicMock()
        client.events.side_effect = _side_effect

        result = _subscribe_event_stream(client)
        # Must be iterable and yield the expected event
        events = list(result)
        self.assertEqual(events, fallback_events)

    def test_fallback_logs_warning(self):
        """Filter failure must be logged as a warning, not silently discarded."""
        def _side_effect(*args, **kwargs):
            if kwargs.get("filters") is not None:
                raise RuntimeError("unsupported filter")
            return iter([])

        client = MagicMock()
        client.events.side_effect = _side_effect

        with self.assertLogs("docker_topology_live.events", level="WARNING") as cm:
            _subscribe_event_stream(client)

        self.assertTrue(
            any("filter" in msg.lower() or "fallback" in msg.lower()
                for msg in cm.output),
            f"Expected a warning about filter fallback; got: {cm.output}",
        )

    def test_fallback_decode_true_in_unfiltered_call(self):
        """Fallback unfiltered call must still request decode=True."""
        def _side_effect(*args, **kwargs):
            if kwargs.get("filters") is not None:
                raise Exception("nope")
            return iter([])

        client = MagicMock()
        client.events.side_effect = _side_effect

        _subscribe_event_stream(client)
        second_call = client.events.call_args_list[1]
        self.assertTrue(
            second_call[1].get("decode") or (len(second_call[0]) > 0),
            "Fallback call should pass decode=True",
        )


# ── stream_live() with API-side filters ───────────────────────────────────────

def _mock_docker_filtered(events_iter, filter_raises=None, from_env_raises=None):
    """Build a mock docker module for filter-related stream_live tests.

    Parameters
    ----------
    events_iter:
        Iterable of raw event dicts returned by client.events().
    filter_raises:
        If set, client.events() raises this exception when called with
        ``filters=`` kwarg (simulating filter-not-supported scenario).
        Falls through to returning events_iter on the second (unfiltered) call.
    from_env_raises:
        If set, docker.from_env() raises this exception.
    """
    mock_docker = MagicMock()
    if from_env_raises is not None:
        mock_docker.from_env.side_effect = from_env_raises
        return mock_docker

    client = MagicMock()
    events_list = list(events_iter)

    if filter_raises is not None:
        call_count = [0]

        def _events(*args, **kwargs):
            call_count[0] += 1
            if kwargs.get("filters") is not None:
                raise filter_raises
            return iter(events_list)

        client.events.side_effect = _events
    else:
        client.events.return_value = iter(events_list)

    mock_docker.from_env.return_value = client
    return mock_docker


class TestStreamLiveWithFilters(unittest.TestCase):
    """stream_live() must use API-side filters and retain Python-side filtering."""

    def _run(self, events, filter_raises=None, from_env_raises=None, scan_fn=None):
        buf = io.BytesIO()
        writer = SSEWriter(buf)
        if scan_fn is None:
            from docker_topology_live.scanner import build_sample
            scan_fn = build_sample
        mock_docker = _mock_docker_filtered(
            events,
            filter_raises=filter_raises,
            from_env_raises=from_env_raises,
        )
        with patch.dict(sys.modules, {"docker": mock_docker}):
            stream_live(writer, scan_fn)
        return buf.getvalue().decode(), mock_docker

    def test_stream_live_passes_filters_to_client_events(self):
        """stream_live() must call client.events() with filters=."""
        _text, mock_docker = self._run([])
        client = mock_docker.from_env.return_value
        # client.events must have been called with filters=
        all_call_kwargs = [c[1] for c in client.events.call_args_list]
        self.assertTrue(
            any("filters" in kw for kw in all_call_kwargs),
            "stream_live() must pass filters= to client.events()",
        )

    def test_filters_passed_are_correct(self):
        """The filters passed by stream_live() must equal docker_event_filters()."""
        _text, mock_docker = self._run([])
        client = mock_docker.from_env.return_value
        filtered_calls = [
            c[1] for c in client.events.call_args_list
            if "filters" in c[1]
        ]
        self.assertTrue(filtered_calls,
                        "No call with filters= found on client.events()")
        self.assertEqual(filtered_calls[0]["filters"], docker_event_filters())

    def test_python_side_filtering_still_active_with_filters(self):
        """is_relevant_event() must still discard irrelevant events even via filtered stream."""
        # An image:pull event should NOT produce a docker-event SSE even if
        # it somehow passes through the API filter (defense-in-depth).
        irrelevant = {
            "Type": "image", "Action": "pull",
            "Actor": {"ID": "sha256:abc", "Attributes": {}}, "time": 1,
        }
        text, _mock = self._run([irrelevant])
        self.assertNotIn("event: docker-event\n", text,
                         "Irrelevant events must be filtered by Python even if API filter missed them")

    def test_relevant_event_produces_docker_event_sse_with_filters(self):
        """A relevant event must produce a docker-event SSE when filters are active."""
        relevant = {
            "Type": "container", "Action": "start",
            "Actor": {"ID": "abc", "Attributes": {"name": "web"}}, "time": 1,
        }
        text, _mock = self._run([relevant])
        self.assertIn("event: docker-event\n", text)

    def test_fallback_when_filter_not_supported(self):
        """If filtered client.events() raises, stream_live must not crash."""
        relevant = {
            "Type": "container", "Action": "stop",
            "Actor": {"ID": "xyz", "Attributes": {"name": "db"}}, "time": 2,
        }
        text, _mock = self._run(
            [relevant],
            filter_raises=RuntimeError("Docker does not support event filters"),
        )
        # The SSE output must still include the initial topology and the event
        self.assertIn("event: topology\n", text)
        self.assertIn("event: docker-event\n", text)

    def test_fallback_no_traceback_in_sse(self):
        """Fallback path must not leak tracebacks to the SSE client."""
        text, _mock = self._run(
            [],
            filter_raises=Exception("filter rejected"),
        )
        self.assertNotIn("Traceback", text)
        self.assertNotIn('File "', text)

    def test_fallback_logs_warning_not_exception(self):
        """Filter failure must be logged as WARNING, not as an unhandled exception."""
        with self.assertLogs("docker_topology_live.events", level="WARNING") as cm:
            self._run(
                [],
                filter_raises=Exception("unsupported filter shape"),
            )
        # Should see a WARNING about filters, not an ERROR traceback
        warning_msgs = [m for m in cm.output if "WARNING" in m]
        self.assertTrue(
            any("filter" in m.lower() or "fallback" in m.lower()
                for m in warning_msgs),
            f"Expected a WARNING about filter unavailability; log output: {cm.output}",
        )

    def test_irrelevant_events_still_ignored_after_fallback(self):
        """After falling back to unfiltered stream, Python-side filter must still work."""
        irrelevant = {
            "Type": "volume", "Action": "create",
            "Actor": {"ID": "vol1", "Attributes": {}}, "time": 3,
        }
        text, _mock = self._run(
            [irrelevant],
            filter_raises=Exception("filters not available"),
        )
        self.assertNotIn("event: docker-event\n", text)

    def test_initial_topology_always_sent_with_filters(self):
        """The initial topology snapshot must always be sent, even with filters."""
        text, _mock = self._run([])
        self.assertIn("event: topology\n", text)

    def test_no_raw_event_fields_in_docker_event_sse(self):
        """docker-event SSE must contain only normalized fields, not raw Docker data."""
        raw = {
            "Type": "container", "Action": "start",
            "Actor": {
                "ID": "abc123",
                "Attributes": {"name": "web", "image": "nginx:latest"},
            },
            "time": 1000,
            # Fields that must NOT appear in the normalized output
            "Env": ["SECRET=hunter2"],
            "HostConfig": {"Binds": ["/etc:/etc"]},
        }
        text, _mock = self._run([raw])
        # Find docker-event data
        for block in text.split("\n\n"):
            lines = block.strip().splitlines()
            if any(line == "event: docker-event" for line in lines):
                data_lines = [l[6:] for l in lines if l.startswith("data: ")]
                event_data = json.loads("\n".join(data_lines))
                # Only normalized keys may appear
                allowed = {"type", "action", "id", "name", "time", "scope"}
                self.assertEqual(
                    set(event_data.keys()), allowed,
                    f"docker-event must contain only {allowed}; got {set(event_data.keys())}",
                )
                # Sensitive raw fields must not appear
                self.assertNotIn("Env", event_data)
                self.assertNotIn("HostConfig", event_data)
                break


class TestIsRelevantEventUnchanged(unittest.TestCase):
    """is_relevant_event() must behave exactly as before Goal 10."""

    def test_container_start_is_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "start"}))

    def test_network_connect_is_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "network", "Action": "connect"}))

    def test_image_pull_not_relevant(self):
        self.assertFalse(is_relevant_event({"Type": "image", "Action": "pull"}))

    def test_volume_create_not_relevant(self):
        self.assertFalse(is_relevant_event({"Type": "volume", "Action": "create"}))

    def test_missing_type_not_relevant(self):
        self.assertFalse(is_relevant_event({"Action": "start"}))

    def test_missing_action_not_relevant(self):
        self.assertFalse(is_relevant_event({"Type": "container"}))

    def test_all_relevant_types_and_actions(self):
        """Every combination of relevant type + action must return True."""
        for t in _RELEVANT_TYPES:
            for a in _RELEVANT_ACTIONS:
                with self.subTest(type=t, action=a):
                    self.assertTrue(
                        is_relevant_event({"Type": t, "Action": a}),
                        f"Expected is_relevant_event to be True for type={t!r} action={a!r}",
                    )


if __name__ == "__main__":
    unittest.main()
