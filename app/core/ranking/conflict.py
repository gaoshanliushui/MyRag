"""
Cross-Evidence Conflict Detection

Detect contradictions between retrieved chunks for hallucination suppression.
"""

import re
import time
from typing import Any

from app.utils.logging import get_logger

logger = get_logger("core.ranking.conflict")


class ConflictDetector:
    """
    Detect contradictions in retrieved evidence.

    Methods:
    - Numerical contradiction detection
    - Factual claim comparison
    - Temporal consistency check

    For full implementation, would use NLI model.
    """

    def __init__(self):
        # Patterns for potential conflicts
        self.numeric_pattern = re.compile(r"\d+\.?\d*")
        self.date_pattern = re.compile(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}")

    async def detect_conflicts(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Detect conflicts between retrieved chunks.

        Args:
            candidates: Ranked candidates

        Returns:
            List of conflict information
        """
        start_time = time.time()

        conflicts = []

        # Compare top candidates pairwise
        n = len(candidates)
        if n < 2:
            return []

        for i in range(min(n, 5)):  # Check top 5
            for j in range(i + 1, min(n, 5)):
                conflict = self._check_pair_conflict(
                    candidates[i],
                    candidates[j],
                )

                if conflict:
                    conflicts.append(conflict)

        latency = (time.time() - start_time) * 1000

        logger.debug(
            f"Conflict detection: checked {min(n, 5)} pairs, "
            f"found {len(conflicts)} conflicts in {latency:.2f}ms"
        )

        return conflicts

    def _check_pair_conflict(
        self,
        candidate1: dict[str, Any],
        candidate2: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Check for conflict between two candidates.

        Returns conflict info if detected, None otherwise.
        """
        content1 = candidate1.get("content", "")
        content2 = candidate2.get("content", "")

        # 1. Check numerical contradictions
        nums1 = self.numeric_pattern.findall(content1)
        nums2 = self.numeric_pattern.findall(content2)

        # Look for same context but different numbers
        # Simplified: if both have numbers and they differ significantly
        if nums1 and nums2:
            # Extract key numbers (e.g., percentages, amounts)
            key_nums1 = [float(n) for n in nums1 if float(n) > 10]
            key_nums2 = [float(n) for n in nums2 if float(n) > 10]

            # Check for significant difference
            for n1 in key_nums1:
                for n2 in key_nums2:
                    if abs(n1 - n2) > 0.5 * max(n1, n2):
                        # Potential numerical conflict
                        return {
                            "type": "numeric",
                            "claim": f"数值差异: {n1} vs {n2}",
                            "supporting_chunks": [str(candidate1.get("chunk_id"))],
                            "contradicting_chunks": [str(candidate2.get("chunk_id"))],
                            "confidence": 0.6,
                            "resolution": None,
                        }

        # 2. Check date contradictions
        dates1 = self.date_pattern.findall(content1)
        dates2 = self.date_pattern.findall(content2)

        if dates1 and dates2 and dates1[0] != dates2[0]:
            return {
                "type": "temporal",
                "claim": f"时间差异: {dates1[0]} vs {dates2[0]}",
                "supporting_chunks": [str(candidate1.get("chunk_id"))],
                "contradicting_chunks": [str(candidate2.get("chunk_id"))],
                "confidence": 0.5,
                "resolution": None,
            }

        # 3. Check negation patterns (simplified)
        negations = ["不", "没有", "否", "不是", "no", "not", "never"]
        has_negation1 = any(neg in content1.lower() for neg in negations)
        has_negation2 = any(neg in content2.lower() for neg in negations)

        # If one says X and other says NOT X (very simplified)
        if has_negation1 != has_negation2:
            # Check if they're talking about same topic
            # (Would need proper NLI for this)
            keywords1 = set(re.findall(r"\b\w{3,}\b", content1.lower()))
            keywords2 = set(re.findall(r"\b\w{3,}\b", content2.lower()))

            overlap = keywords1 & keywords2
            if len(overlap) > 3:
                return {
                    "type": "factual",
                    "claim": "可能的陈述冲突",
                    "supporting_chunks": [str(candidate1.get("chunk_id"))],
                    "contradicting_chunks": [str(candidate2.get("chunk_id"))],
                    "confidence": 0.4,
                    "resolution": None,
                }

        return None

    def generate_resolution(
        self,
        conflict: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> str | None:
        """
        Generate resolution for detected conflict.

        In production, would use LLM to analyze and resolve.
        """
        # Simplified resolution logic
        conflict_type = conflict.get("type")

        if conflict_type == "numeric":
            # Prefer more recent or authoritative source
            return "数值存在差异，建议核对原始文档"

        elif conflict_type == "temporal":
            return "时间记载存在差异，建议参考最新版本"

        elif conflict_type == "factual":
            return "陈述存在冲突，建议综合多方来源判断"

        return None


def get_conflict_detector() -> ConflictDetector:
    """Get conflict detector instance."""
    return ConflictDetector()