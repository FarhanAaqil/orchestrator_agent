"""
orchestrator_core/storage/chroma_client.py

Scoped ChromaDB client wrapper for the supported orchestrator agents:
Career, Research, Growth/Content, Critic, Info, Email, GitHub, LinkedIn, and General Chat.

Ensures lazy initialization without import-time side effects, and prevents
unsupported experimental agents from creating or accessing collections.
"""

from typing import Any, Optional
from orchestrator_core.config import get_settings


SUPPORTED_AGENTS = {
    "career_agent",
    "research_agent",
    "growth_content_agent",
    "critic_agent",
    "info_agent",
    "email_agent",
    "github_agent",
    "linkedin_agent",
    "general_chat_agent",
}


def get_chroma_client(persist_directory: Optional[str] = None) -> Any:
    """Lazily instantiate and return a PersistentClient instance."""
    import chromadb

    if persist_directory is None:
        persist_directory = get_settings().chroma_db_dir

    return chromadb.PersistentClient(path=persist_directory)


def get_agent_collection(agent_name: str, client: Optional[Any] = None) -> Any:
    """
    Retrieve or create a collection for a supported agent.
    Raises ValueError if an unsupported agent name is provided.
    """
    normalized_name = agent_name.strip().lower()
    if normalized_name not in SUPPORTED_AGENTS:
        raise ValueError(
            f"Agent '{agent_name}' is not supported. "
            f"ChromaDB access is strictly scoped to: {sorted(SUPPORTED_AGENTS)}"
        )

    if client is None:
        client = get_chroma_client()

    collection_name = f"orchestrator_{normalized_name}"
    return client.get_or_create_collection(name=collection_name)
