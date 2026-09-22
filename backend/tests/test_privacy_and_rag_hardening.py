"""
Privacy and RAG Hardening Tests (Sections 24-31, 34-35).
Covers:
1. Canonical user purge across all private artifacts (memory, knowledge, vectors, identities, conversation traces)
2. Vector deletion failure fails closed (raises, session rollbacks, no false deletion claims)
3. RAG disabled returns 409 Conflict for vector-dependent endpoints
4. Persistent encryption key and automatic migration of legacy fallback ciphertext
"""

import os
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.ai.rag.vector_store import FakeVectorStore, VectorStoreError
from app.api.deps import get_current_admin
from app.database import get_session
from app.main import app
from app.models.ai import KnowledgeChunk, KnowledgeDocument, KnowledgeSource, MemoryItem
from app.models.config import BotConfig
from app.models.user import User, UserIdentity
from app.schemas.auth import AdminUser
from app.services.data_retention import purge_user_data
from app.services.runtime_config import (
    KEY_SIGNAL_API_TOKEN_ENC,
    decrypt_value,
    migrate_legacy_encrypted_settings,
)


@pytest.mark.asyncio
async def test_canonical_user_purge_covers_all_artifacts(session):
    """Purging by phone number or alias resolves canonical user and wipes all user-scoped artifacts."""
    # 1. Create canonical user with aliases
    user = User(
        signal_id="sig_user_123",
        phone_number="+420777111222",
        display_name="Alice Smith",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    alice_id = user.id

    ident = UserIdentity(
        user_id=alice_id,
        identity_type="phone",
        identity_value="+420777111222",
    )
    session.add(ident)

    # 2. Add user-scoped knowledge document and chunk
    source = KnowledgeSource(title="User Uploads", source_type="manual")
    session.add(source)
    await session.commit()
    await session.refresh(source)

    doc = KnowledgeDocument(
        source_id=source.id,
        title="Alice Private Notes",
        content="Sensitive personal preferences",
        scope_type="user",
        scope_id=str(alice_id),
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    chunk = KnowledgeChunk(
        document_id=doc.id,
        source_id=source.id,
        chunk_index=0,
        content="Sensitive personal preferences",
        scope_type="user",
        scope_id=str(alice_id),
        vector_id="vec_alice_001",
    )
    session.add(chunk)

    # 3. Add user memory
    memory = MemoryItem(
        scope_type="user",
        scope_id=str(alice_id),
        memory_type="preference",
        content="Prefers organic dark roast",
    )
    session.add(memory)
    await session.commit()

    # 4. Mock vector store
    fake_vec = FakeVectorStore()
    await fake_vec.upsert(
        "knowledge", [{"id": "vec_alice_001", "vector": [0.1] * 8, "payload": {}}]
    )

    # 5. Purge by phone number instead of raw user.id (canonical resolution test)
    result = await purge_user_data(session, identifier="+420777111222", vector_store=fake_vec)

    assert result["canonical_scope_id"] == str(alice_id)
    assert result["users_deleted"] == 1
    assert result["vectors_deleted"] == 1
    assert result["memories_deleted"] >= 1
    assert result["chunks_deleted"] >= 1

    # 6. Verify relational rows deleted
    u_after = (await session.execute(select(User).where(User.id == alice_id))).scalar_one_or_none()
    assert u_after is None

    chunks_after = (
        (
            await session.execute(
                select(KnowledgeChunk).where(KnowledgeChunk.scope_id == str(alice_id))
            )
        )
        .scalars()
        .all()
    )
    assert len(chunks_after) == 0

    mem_after = (
        (await session.execute(select(MemoryItem).where(MemoryItem.scope_id == str(alice_id))))
        .scalars()
        .all()
    )
    assert len(mem_after) == 0


@pytest.mark.asyncio
async def test_privacy_erasure_fails_closed_on_vector_deletion_failure(session):
    """If vector deletion fails, purge must raise, rollback, and NOT delete relational rows."""
    user = User(
        signal_id="sig_fail_closed",
        phone_number="+420777999119",
        display_name="Bob FailClosed",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    bob_id = user.id

    source = KnowledgeSource(title="Bob Sources", source_type="manual")
    session.add(source)
    await session.commit()
    await session.refresh(source)

    doc = KnowledgeDocument(
        source_id=source.id,
        title="Bob Doc",
        content="Private text",
        scope_type="user",
        scope_id=str(bob_id),
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    chunk = KnowledgeChunk(
        document_id=doc.id,
        source_id=source.id,
        chunk_index=0,
        content="Private text",
        scope_type="user",
        scope_id=str(bob_id),
        vector_id="vec_bob_fail",
    )
    session.add(chunk)
    await session.commit()

    # Create vector store that fails on delete
    failing_vec = FakeVectorStore()
    failing_vec.delete = AsyncMock(side_effect=VectorStoreError("Qdrant connection dropped"))

    with pytest.raises(RuntimeError, match="Vector deletion failed"):
        await purge_user_data(session, identifier="+420777999119", vector_store=failing_vec)

    # Assert relational rows NOT deleted due to fail-closed rollback
    u_still_exists = (
        await session.execute(select(User).where(User.id == bob_id))
    ).scalar_one_or_none()
    assert u_still_exists is not None


@pytest.mark.asyncio
async def test_rag_disabled_returns_409_conflict(session, monkeypatch):
    """When RAG is disabled, knowledge endpoints must return 409 Conflict instead of 500 error."""
    # Set rag_enabled = False in DB config
    cfg_row = BotConfig(key="rag_enabled", value="false")
    session.add(cfg_row)
    await session.commit()

    app.dependency_overrides[get_current_admin] = lambda: AdminUser(username="rag_tester")
    app.dependency_overrides[get_session] = lambda: session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": "Bearer test-token"},
        ) as client:
            r = await client.post(
                "/api/ai-studio/knowledge/search",
                params={"query": "coffee"},
            )
            assert r.status_code == 409
            assert "RAG is disabled" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        await session.delete(cfg_row)
        await session.commit()


@pytest.mark.asyncio
async def test_persistent_master_key_and_legacy_migration(session, monkeypatch, tmp_path):
    """Verify persistent master key creation and transparent re-encryption of legacy ciphertext."""
    from app.services import runtime_config
    from app.services.runtime_config import _get_legacy_fallback_fernet

    # Set master key file path to isolated temp directory
    key_file = tmp_path / ".master_key"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CONFIG_ENCRYPTION_KEY", raising=False)
    runtime_config._MASTER_KEY_CACHE = None

    # Encrypt a secret using the old legacy fallback key
    legacy_ciphertext = (
        _get_legacy_fallback_fernet().encrypt(b"my-precious-signal-token").decode("utf-8")
    )

    # Store legacy ciphertext in DB
    session.add(BotConfig(key=KEY_SIGNAL_API_TOKEN_ENC, value=legacy_ciphertext))
    await session.commit()

    # Run startup migration
    migrated_count = await migrate_legacy_encrypted_settings(session)
    assert migrated_count >= 1

    # Verify that the value is now decryptable using current master key
    cfg = (
        await session.execute(select(BotConfig).where(BotConfig.key == KEY_SIGNAL_API_TOKEN_ENC))
    ).scalar_one()
    assert cfg.value != legacy_ciphertext

    decrypted = decrypt_value(cfg.value)
    assert decrypted == "my-precious-signal-token"

    # Verify master key file was created with 0600 permissions
    assert key_file.exists()
    mode = oct(os.stat(key_file).st_mode & 0o777)
    assert mode == "0o600"
