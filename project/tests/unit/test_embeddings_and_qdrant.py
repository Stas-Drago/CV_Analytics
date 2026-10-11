from math import sqrt
from types import SimpleNamespace

import pytest
from qdrant_client.models import Distance, VectorParams

from surveillance.analysis.embeddings import LabseEmbedder
from surveillance.storage.qdrant import QdrantEventIndex, VECTOR_SIZE


class Values:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeSentenceTransformer:
    def __init__(self, values):
        self.values = values

    def encode(self, _text, normalize_embeddings):
        assert normalize_embeddings is True
        return Values(self.values)


def test_labse_embedding_is_768_dimensional_and_normalized() -> None:
    embedder = LabseEmbedder("fake", model=FakeSentenceTransformer([1.0] * VECTOR_SIZE))
    embedding = embedder.encode("Описание на русском")
    assert len(embedding) == VECTOR_SIZE
    assert sum(value * value for value in embedding) == pytest.approx(1.0)


def test_labse_rejects_unexpected_dimension() -> None:
    embedder = LabseEmbedder("fake", model=FakeSentenceTransformer([1.0, 2.0]))
    with pytest.raises(ValueError, match="768"):
        embedder.encode("Описание")


class FakeQdrantClient:
    def __init__(self, exists=False, vectors=None):
        self.exists, self.vectors = exists, vectors
        self.created, self.points = [], []

    def collection_exists(self, _collection):
        return self.exists

    def create_collection(self, collection_name, vectors_config):
        self.created.append((collection_name, vectors_config))

    def get_collection(self, _collection):
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=self.vectors)))

    def upsert(self, collection_name, points):
        self.points.append((collection_name, points))


def test_qdrant_creates_versioned_collection_and_uses_stable_point_id() -> None:
    client = FakeQdrantClient()
    index = QdrantEventIndex("http://unused", client=client)
    index.ensure_collection()
    index.upsert("00000000-0000-0000-0000-000000000001", [1 / sqrt(VECTOR_SIZE)] * VECTOR_SIZE, {"event_id": "x"})

    assert client.created[0][0] == "surveillance_events_labse_v1"
    assert client.created[0][1].size == VECTOR_SIZE
    assert client.points[0][1][0].id == "00000000-0000-0000-0000-000000000001"


def test_qdrant_rejects_incompatible_existing_collection() -> None:
    client = FakeQdrantClient(True, VectorParams(size=384, distance=Distance.COSINE))
    with pytest.raises(ValueError, match="768"):
        QdrantEventIndex("http://unused", client=client).ensure_collection()
