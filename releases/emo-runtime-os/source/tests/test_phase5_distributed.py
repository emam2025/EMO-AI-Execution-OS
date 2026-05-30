"""Phase 5 — Distributed Runtime tests.

Tests for remote mesh transport, distributed registry, and MeshNode.
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.runtime.mesh import (
    MeshEnvelope,
    MeshMessageType,
    MeshProtocol,
    ServiceRegistry,
    MeshNode,
    PeerNode,
    DistributedRegistry,
    RemoteTransportClient,
    RemoteTransportServer,
    RemoteTransportError,
    envelope_to_dict,
    dict_to_envelope,
    envelope_to_json,
    json_to_envelope,
)
from core.runtime.mesh.service_mesh import ServiceNotAvailable


# ═══════════════════════════════════════════════════════════════════
# Remote Serialization
# ═══════════════════════════════════════════════════════════════════

class TestRemoteSerialization:
    def test_envelope_to_dict(self):
        env = MeshProtocol.create_request("scheduler", "order", {"dag": "x"})
        d = envelope_to_dict(env)
        assert d["service"] == "scheduler"
        assert d["method"] == "order"
        assert d["msg_type"] == "request"

    def test_dict_to_envelope(self):
        d = {
            "msg_type": "request",
            "service": "scheduler",
            "method": "order",
            "payload": {"dag": "x"},
            "trace_id": "abc",
            "correlation_id": "",
            "ttl": 30.0,
            "priority": 0,
        }
        env = dict_to_envelope(d)
        assert env.service == "scheduler"
        assert env.method == "order"
        assert env.msg_type == MeshMessageType.REQUEST

    def test_envelope_to_json_roundtrip(self):
        original = MeshProtocol.create_request("scheduler", "order", {"dag": "x"}, trace_id="t1")
        json_str = envelope_to_json(original)
        restored = json_to_envelope(json_str)
        assert restored.service == original.service
        assert restored.method == original.method
        assert restored.payload == original.payload
        assert restored.trace_id == original.trace_id

    def test_dict_to_envelope_all_types(self):
        for msg_type in MeshMessageType:
            d = {
                "msg_type": msg_type.value,
                "service": "test",
                "method": "ping",
                "payload": {},
                "trace_id": "",
                "correlation_id": "",
                "ttl": 30.0,
                "priority": 0,
            }
            env = dict_to_envelope(d)
            assert env.msg_type == msg_type

    def test_envelope_to_json_preserves_nested(self):
        env = MeshProtocol.create_request("svc", "m", {"items": [1, 2, 3], "nested": {"a": 1}})
        restored = json_to_envelope(envelope_to_json(env))
        assert restored.payload["items"] == [1, 2, 3]
        assert restored.payload["nested"]["a"] == 1

    def test_response_roundtrip(self):
        req = MeshProtocol.create_request("svc", "m", {"x": 1})
        resp = MeshProtocol.create_response(req, {"result": "ok"})
        restored = json_to_envelope(envelope_to_json(resp))
        assert restored.msg_type == MeshMessageType.RESPONSE
        assert restored.payload == {"result": "ok"}


# ═══════════════════════════════════════════════════════════════════
# Remote Transport
# ═══════════════════════════════════════════════════════════════════

class TestRemoteTransportClient:
    def test_send_request_http_error(self):
        client = RemoteTransportClient("http://127.0.0.1:1")
        env = MeshProtocol.create_request("test", "ping", {})
        with pytest.raises(RemoteTransportError):
            client.send_request(env)

    def test_send_heartbeat_failure(self):
        client = RemoteTransportClient("http://127.0.0.1:1")
        env = MeshProtocol.create_request("test", "ping", {})
        assert client.send_heartbeat(env) is False

    def test_register_remote_failure(self):
        client = RemoteTransportClient("http://127.0.0.1:1")
        assert client.register_remote("test", "i1", "host", 1) is False


class TestRemoteTransportServer:
    def test_start_and_shutdown(self):
        server = RemoteTransportServer(host="127.0.0.1", port=0)
        server.start()
        assert server.port > 0
        time.sleep(0.05)
        server.shutdown()

    def test_dispatch_request(self):
        results = []
        def dispatch(env):
            results.append(env)
            return MeshProtocol.create_response(env, {"echo": env.payload})

        server = RemoteTransportServer(
            host="127.0.0.1",
            port=0,
            dispatch_fn=dispatch,
        )
        server.start()
        time.sleep(0.05)

        client = RemoteTransportClient(f"http://127.0.0.1:{server.port}")
        req = MeshProtocol.create_request("test", "ping", {"msg": "hello"})
        resp = client.send_request(req)

        assert resp.payload == {"echo": {"msg": "hello"}}
        assert len(results) == 1
        server.shutdown()

    def test_heartbeat_endpoint(self):
        server = RemoteTransportServer(host="127.0.0.1", port=0)
        server.start()
        time.sleep(0.05)

        with httpx.Client() as client:
            resp = client.post(
                f"http://127.0.0.1:{server.port}/mesh/heartbeat",
                json={"service": "test"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

        server.shutdown()

    def test_unknown_path_returns_404(self):
        server = RemoteTransportServer(host="127.0.0.1", port=0)
        server.start()
        time.sleep(0.05)

        with httpx.Client() as client:
            resp = client.post(
                f"http://127.0.0.1:{server.port}/unknown",
                json={},
            )
            assert resp.status_code == 404

        server.shutdown()


# ═══════════════════════════════════════════════════════════════════
# Distributed Registry
# ═══════════════════════════════════════════════════════════════════

class TestDistributedRegistry:
    def test_local_registry_delegation(self):
        reg = DistributedRegistry()
        iid = reg.local.register("scheduler")
        assert reg.local.discover("scheduler")[0].instance_id == iid

    def test_register_peer(self):
        reg = DistributedRegistry()
        peer = reg.register_peer("node-1", "10.0.0.1", 9001)
        assert peer.node_id == "node-1"
        assert peer.host == "10.0.0.1"
        assert "node-1" in reg.peers

    def test_remove_peer(self):
        reg = DistributedRegistry()
        reg.register_peer("node-1", "10.0.0.1", 9001)
        assert reg.remove_peer("node-1") is True
        assert reg.remove_peer("nonexistent") is False

    def test_peers_property_thread_safe(self):
        reg = DistributedRegistry()
        peers = reg.peers
        assert isinstance(peers, dict)

    def test_discover_remote_empty_when_no_peers(self):
        reg = DistributedRegistry()
        results = reg.discover_remote("scheduler")
        assert results == []

    def test_check_peer_health_empty(self):
        reg = DistributedRegistry()
        results = reg.check_peer_health()
        assert results == {}

    def test_announce_empty_when_no_peers(self):
        reg = DistributedRegistry()
        assert reg.announce("svc", "i1", "host", 1) == 0


# ═══════════════════════════════════════════════════════════════════
# MeshNode
# ═══════════════════════════════════════════════════════════════════

class TestMeshNode:
    def test_create_node(self):
        node = MeshNode(node_id="test-1", host="127.0.0.1")
        assert node.node_id == "test-1"
        assert node.host == "127.0.0.1"

    def test_start_and_shutdown(self):
        node = MeshNode(node_id="test-1", host="127.0.0.1")
        node.start()
        assert node.port > 0
        node.shutdown()

    def test_register_handler(self):
        node = MeshNode(node_id="test-1")
        called = []
        def handler(payload):
            called.append(payload)
            return {"result": "ok"}

        node.register_handler("test_svc", "ping", handler)
        result = node.mesh.call("test_svc", "ping", {"data": 1})
        assert result["result"] == "ok"
        assert called == [{"data": 1}]

    def test_add_peer(self):
        node = MeshNode(node_id="test-1")
        peer = node.add_peer("peer-1", "10.0.0.2", 9002)
        assert peer.node_id == "peer-1"
        assert len(node.distributed_registry.peers) == 1

    def test_remove_peer(self):
        node = MeshNode(node_id="test-1")
        node.add_peer("peer-1", "10.0.0.2", 9002)
        assert node.remove_peer("peer-1") is True
        assert node.remove_peer("nonexistent") is False

    def test_call_remote_unknown_peer_raises(self):
        node = MeshNode(node_id="test-1")
        with pytest.raises(ValueError, match="Unknown peer"):
            node.call_remote("svc", "method", {}, "nonexistent")

    def test_discover_remote_empty_when_no_peers(self):
        node = MeshNode(node_id="test-1")
        assert node.discover_remote("scheduler") == []

    def test_announce_to_peers_empty(self):
        node = MeshNode(node_id="test-1")
        node.register_handler("svc", "ping", lambda p: {"ok": True})
        # Register the service in the registry
        node.registry.register("svc")
        assert node.announce_to_peers() == 0

    def test_registry_property(self):
        node = MeshNode(node_id="test-1")
        assert node.registry is not None
        assert node.registry is node.mesh.registry
        assert node.registry is node.distributed_registry.local

    def test_two_nodes_communicate(self):
        """Integration: two local MeshNodes communicate via HTTP."""
        node_a = MeshNode(node_id="node-a", host="127.0.0.1")
        node_b = MeshNode(node_id="node-b", host="127.0.0.1")

        results = []
        def handler_b(payload):
            results.append(payload)
            return {"echo": payload}

        node_b.register_handler("svc", "ping", handler_b)
        node_b.start()

        node_a.add_peer("node-b", "127.0.0.1", node_b.port)
        node_a.start()

        time.sleep(0.1)

        resp = node_a.call_remote("svc", "ping", {"msg": "hello"}, "node-b")
        assert resp["echo"]["msg"] == "hello"
        assert len(results) == 1

        node_a.shutdown()
        node_b.shutdown()

    def test_remote_handler_error_returns_error_response(self):
        node_a = MeshNode(node_id="node-a", host="127.0.0.1")
        node_b = MeshNode(node_id="node-b", host="127.0.0.1")

        def failing_handler(payload):
            raise ValueError("Something went wrong")

        node_b.register_handler("svc", "fail", failing_handler)
        node_b.start()

        node_a.add_peer("node-b", "127.0.0.1", node_b.port)
        node_a.start()

        time.sleep(0.1)

        resp = node_a.call_remote("svc", "fail", {}, "node-b")
        assert "error" in resp
        assert "Something went wrong" in resp["error"]

        node_a.shutdown()
        node_b.shutdown()

    def test_mesh_node_auto_id(self):
        node = MeshNode()
        assert len(node.node_id) == 12
