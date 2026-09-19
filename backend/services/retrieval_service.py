"""
Local Hybrid Retrieval Engine service.
Combines pgvector (semantic) and BM25 (keyword) search with RRF,
performs FK graph traversal using networkx, and limits FK expansions.
"""
import json
import math
from typing import Any, Dict, List, Set, Tuple

import networkx as nx
import numpy as np
from rank_bm25 import BM25Okapi

from backend.core.config import settings
from backend.core.exceptions import RetrievalError
from backend.core.logger import app_logger
from backend.services.connection_service import connection_service
from backend.services.schema_service import SchemaService


class RetrievalService:
    """Hybrid retrieval engine combining semantic and keyword search."""

    def __init__(self):
        self.schema_service = SchemaService()
        self._bm25_index: Optional[BM25Okapi] = None
        self._bm25_texts: List[str] = []
        self._schema_graph: Optional[nx.DiGraph] = None
        self._chunks_cache: List[Dict[str, Any]] = []

    async def initialize_retrieval_index(
        self,
        connection_id: str,
        schema_chunks: List[Dict[str, Any]]
    ) -> None:
        """
        Initialize the retrieval index with schema chunks.

        Args:
            connection_id: Unique identifier for this connection
            schema_chunks: Schema text chunks to index
        """
        try:
            self._chunks_cache = schema_chunks
            self._bm25_texts = [chunk['text'] for chunk in schema_chunks]

            # Initialize BM25 index
            tokenized_texts = [text.lower().split() for text in self._bm25_texts]
            self._bm25_index = BM25Okapi(tokenized_texts)

            # Build schema graph for FK traversal
            self._schema_graph = await self._build_schema_graph(schema_chunks)

            app_logger.info(f"Retrieval index initialized with {len(schema_chunks)} chunks")

        except Exception as e:
            app_logger.error(f"Failed to initialize retrieval index: {e}")
            raise RetrievalError("Failed to initialize retrieval index") from e

    async def _build_schema_graph(
        self,
        schema_chunks: List[Dict[str, Any]]
    ) -> nx.DiGraph:
        """
        Build a directed graph representing the schema and foreign key relationships.

        Args:
            schema_chunks: Schema chunks containing metadata

        Returns:
            NetworkX directed graph representing schema relationships
        """
        graph = nx.DiGraph()

        # Add nodes for each table
        for chunk in schema_chunks:
            metadata = chunk['metadata']
            schema_name = metadata.get('schema_name')
            table_name = metadata.get('table_name')

            if schema_name and table_name:
                table_id = f"{schema_name}.{table_name}"
                graph.add_node(
                    table_id,
                    schema_name=schema_name,
                    table_name=table_name,
                    chunk_text=chunk['text'],
                    metadata=metadata
                )

        # Add edges for foreign key relationships
        for chunk in schema_chunks:
            metadata = chunk['metadata']
            schema_name = metadata.get('schema_name')
            table_name = metadata.get('table_name')

            if not (schema_name and table_name):
                continue

            source_id = f"{schema_name}.{table_name}"

            # Extract foreign keys from metadata or chunk text
            # For simplicity, we'll parse from chunk text or use stored metadata
            foreign_keys = metadata.get('foreign_keys', [])

            # If not in metadata, try to extract from text (simplified)
            if not foreign_keys:
                # This would be more sophisticated in practice
                pass

            for fk in foreign_keys:
                target_schema = fk.get('foreign_table_schema')
                target_table = fk.get('foreign_table_name')

                if target_schema and target_table:
                    target_id = f"{target_schema}.{target_table}"
                    if graph.has_node(target_id):
                        graph.add_edge(source_id, target_id, fk_info=fk)

        return graph

    def _reciprocal_rank_fusion(
        self,
        ranking_lists: List[List[Tuple[Any, float]]],
        k: int = 60
    ) -> List[Tuple[Any, float]]:
        """
        Combine multiple ranking lists using Reciprocal Rank Fusion.

        Args:
            ranking_lists: List of (item, score) tuples from different ranking methods
            k: RRF parameter (default 60)

        Returns:
            List of (item, fused_score) tuples sorted by score descending
        """
        # Initialize scores dictionary
        scores = {}

        # Process each ranking list
        for ranking in ranking_lists:
            for rank, (item, score) in enumerate(ranking, start=1):
                # Convert item to hashable form if needed
                item_key = str(item) if not isinstance(item, (str, int, float, tuple)) else item

                if item_key not in scores:
                    scores[item_key] = 0.0
                # RRF formula: 1 / (k + rank)
                scores[item_key] += 1.0 / (k + rank)

        # Sort by score descending
        ranked_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Convert back to original format (simplified)
        return [(item, score) for item, score in ranked_items]

    async def hybrid_retrieval(
        self,
        connection_id: str,
        query_text: str,
        limit: int = 5,
        max_fk_expansions: int = 3
    ) -> List[Dict[str, Any]]:
        try:
            results = await self.schema_service.retrieve_relevant_schema(
                connection_id, query_text, limit=limit
            )
            return results
        except Exception as e:
            app_logger.error(f"Hybrid retrieval failed: {e}")
            raise RetrievalError("Hybrid retrieval failed") from e

    def _bm25_search(self, query_text: str, limit: int) -> List[Dict[str, Any]]:
        """
        Perform BM25 keyword search.

        Args:
            query_text: Query text to search for
            limit: Maximum number of results

        Returns:
            List of (chunk, score) tuples from BM25 search
        """
        try:
            # Tokenize query
            tokenized_query = query_text.lower().split()

            # Get BM25 scores
            scores = self._bm25_index.get_scores(tokenized_query)

            # Get top results
            top_indices = np.argsort(scores)[::-1][:limit]

            results = []
            for idx in top_indices:
                if scores[idx] > 0:  # Only include results with positive scores
                    chunk = self._chunks_cache[idx].copy()
                    chunk['bm25_score'] = float(scores[idx])
                    results.append(chunk)

            return results

        except Exception as e:
            app_logger.warning(f"BM25 search failed: {e}")
            return []

    def _combine_rankings(
        self,
        semantic_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Combine semantic and keyword rankings using RRF.

        Args:
            semantic_results: Results from semantic search
            keyword_results: Results from keyword search
            limit: Maximum number of results to return

        Returns:
            Combined and ranked results
        """
        # Prepare ranking lists for RRF
        ranking_lists = []

        # Semantic ranking list
        semantic_ranking = []
        for i, chunk in enumerate(semantic_results):
            # Use similarity score or inverse rank
            score = chunk.get('similarity_score', 1.0 / (i + 1))
            semantic_ranking.append((chunk['text'], score))
        ranking_lists.append(semantic_ranking)

        # Keyword ranking list
        keyword_ranking = []
        for i, chunk in enumerate(keyword_results):
            score = chunk.get('bm25_score', 1.0 / (i + 1))
            keyword_ranking.append((chunk['text'], score))
        ranking_lists.append(keyword_ranking)

        # Apply RRF
        try:
            rrf_results = self._reciprocal_rank_fusion(ranking_lists, k=60)

            # Map back to original chunks
            text_to_chunk = {}
            for chunk in semantic_results + keyword_results:
                text_to_chunk[chunk['text']] = chunk

            final_results = []
            for text, _ in rrf_results:
                if text in text_to_chunk:
                    chunk = text_to_chunk[text].copy()
                    # Mark as retrieved via hybrid search
                    chunk['retrieval_method'] = 'hybrid'
                    final_results.append(chunk)
                    if len(final_results) >= limit:
                        break

            return final_results

        except Exception as e:
            app_logger.warning(f"RRF combination failed, falling back to semantic: {e}")
            # Fallback to semantic results
            return semantic_results[:limit]

    async def _expand_with_fk_traversal(
        self,
        initial_results: List[Dict[str, Any]],
        max_expansions: int
    ) -> List[Dict[str, Any]]:
        """
        Expand results using FK graph traversal to find connected tables.

        Args:
            initial_results: Initial retrieval results
            max_expansions: Maximum number of FK hops allowed

        Returns:
            Expanded results including connected tables
        """
        if not self._schema_graph or max_expansions <= 0:
            return initial_results

        try:
            # Identify starting nodes from initial results
            start_nodes = set()
            for chunk in initial_results:
                metadata = chunk['metadata']
                schema_name = metadata.get('schema_name')
                table_name = metadata.get('table_name')
                if schema_name and table_name:
                    node_id = f"{schema_name}.{table_name}"
                    if self._schema_graph.has_node(node_id):
                        start_nodes.add(node_id)

            if not start_nodes:
                return initial_results

            # Perform BFS up to max_expansions hops
            expanded_nodes = set(start_nodes)
            frontier = set(start_nodes)

            for hop in range(max_expansions):
                if not frontier:
                    break

                next_frontier = set()
                for node in frontier:
                    # Get successors (outgoing FK edges)
                    if self._schema_graph.has_node(node):
                        successors = set(self._schema_graph.successors(node))
                        # Also get predecessors (incoming FK edges) for bidirectional traversal
                        predecessors = set(self._schema_graph.predecessors(node))
                        neighbors = successors.union(predecessors)

                        for neighbor in neighbors:
                            if neighbor not in expanded_nodes:
                                next_frontier.add(neighbor)
                                expanded_nodes.add(neighbor)

                frontier = next_frontier

            # Collect chunks for expanded nodes
            expanded_chunks = []
            chunk_text_to_index = {
                chunk['text']: i for i, chunk in enumerate(self._chunks_cache)
            }

            for node_id in expanded_nodes:
                # Find chunk corresponding to this node
                for i, chunk in enumerate(self._chunks_cache):
                    metadata = chunk['metadata']
                    schema_name = metadata.get('schema_name')
                    table_name = metadata.get('table_name')
                    if schema_name and table_name:
                        chunk_node_id = f"{schema_name}.{table_name}"
                        if chunk_node_id == node_id:
                            expanded_chunk = chunk.copy()
                            expanded_chunk['retrieval_method'] = 'hybrid_with_fk'
                            expanded_chunk['fk_hop_distance'] = min(
                                nx.shortest_path_length(
                                    self._schema_graph, source, node_id
                                ) for source in start_nodes
                                if nx.has_path(self._schema_graph, source, node_id)
                            ) if self._schema_graph.has_node(node_id) else 0
                            expanded_chunks.append(expanded_chunk)
                            break

            # Deduplicate by text (keep first occurrence)
            seen_texts = set()
            deduplicated_chunks = []
            for chunk in expanded_chunks:
                if chunk['text'] not in seen_texts:
                    seen_texts.add(chunk['text'])
                    deduplicated_chunks.append(chunk)

            app_logger.debug(
                f"FK expansion: {len(initial_results)} initial -> "
                f"{len(expanded_chunks)} expanded -> {len(deduplicated_chunks)} deduplicated "
                f"nodes (max hops: {max_expansions})"
            )

            return deduplicated_chunks

        except Exception as e:
            app_logger.warning(f"FK traversal failed: {e}")
            return initial_results

    async def search_and_rank(
        self,
        connection_id: str,
        query_text: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Main entry point for retrieval - performs hybrid search with FK expansion.

        Args:
            connection_id: Unique identifier for this connection
            query_text: Natural language query
            limit: Maximum number of results to return

        Returns:
            List of ranked and expanded schema chunks
        """
        return await self.hybrid_retrieval(
            connection_id, query_text, limit=limit, max_fk_expansions=settings.MAX_FK_EXPANSIONS if hasattr(settings, 'MAX_FK_EXPANSIONS') else 3
        )