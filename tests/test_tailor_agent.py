import numpy as np

import tailor_agent


class FakeEmbeddings:
    """Stands in for the Gemini client: records each call, returns fixed vectors."""

    def __init__(self, vectors):
        self.vectors = vectors
        self.calls = []

    def embed_content(self, model, contents):
        self.calls.append(list(contents))
        embeddings = [type("E", (), {"values": self.vectors[t]})() for t in contents]
        return type("R", (), {"embeddings": embeddings})()


def test_embed_many_batches_and_caches(monkeypatch):
    fake = FakeEmbeddings({"a": [1.0, 0.0], "b": [0.0, 1.0]})
    monkeypatch.setattr(tailor_agent, "client", type("C", (), {"models": fake})())
    monkeypatch.setattr(tailor_agent, "_embedding_cache", {})

    first = tailor_agent.embed_many(["a", "b", "a"])
    second = tailor_agent.embed_many(["b", "a"])

    assert fake.calls == [["a", "b"]]  # one call, no duplicates, second run fully cached
    assert np.allclose(first[0], [1.0, 0.0]) and np.allclose(second[0], [0.0, 1.0])


def test_score_bullets_sorts_by_similarity(monkeypatch):
    fake = FakeEmbeddings({"close": [1.0, 0.1], "far": [0.0, 1.0]})
    monkeypatch.setattr(tailor_agent, "client", type("C", (), {"models": fake})())
    monkeypatch.setattr(tailor_agent, "_embedding_cache", {})

    scored = tailor_agent.score_bullets(["far", "close"], np.array([1.0, 0.0]))
    assert [b for _, b in scored] == ["close", "far"]
