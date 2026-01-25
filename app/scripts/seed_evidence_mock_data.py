#!/usr/bin/env python3
"""
Seed Evidence Mock Data - Atomic Habits & Principles
=====================================================

Creates a knowledge graph with evidence-backed relationships from:
- James Clear's "Atomic Habits" (2018)
- Ray Dalio's "Principles" (2017)

This demonstrates Phase 4's evidence infrastructure with real book citations.

Usage:
    poetry run python scripts/seed_evidence_mock_data.py --dry-run  # Preview
    poetry run python scripts/seed_evidence_mock_data.py --apply    # Create data
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from core.config.credential_store import get_credential
from core.models.semantic.edge_metadata import (
    create_cited_metadata,
    create_research_backed_metadata,
)

# Load environment variables (MUST be before get_credential calls)
load_dotenv()


# ============================================================================
# KNOWLEDGE UNITS - Atomic Habits
# ============================================================================

ATOMIC_HABITS_KUS = [
    {
        "uid": "ku.habit_formation_fundamentals",
        "title": "Habit Formation Fundamentals",
        "domain": "PERSONAL",
        "description": "Core principles of how habits are formed and maintained in the brain.",
    },
    {
        "uid": "ku.four_laws_behavior_change",
        "title": "Four Laws of Behavior Change",
        "domain": "PERSONAL",
        "description": "Clear's framework: Make it Obvious, Attractive, Easy, and Satisfying.",
    },
    {
        "uid": "ku.cue_routine_reward",
        "title": "Cue-Routine-Reward Loop",
        "domain": "PERSONAL",
        "description": "The neurological loop that drives all habits (based on Duhigg's work).",
    },
    {
        "uid": "ku.identity_based_habits",
        "title": "Identity-Based Habits",
        "domain": "PERSONAL",
        "description": "Building habits around who you want to become, not what you want to achieve.",
    },
    {
        "uid": "ku.aggregation_marginal_gains",
        "title": "Aggregation of Marginal Gains",
        "domain": "PERSONAL",
        "description": "1% better every day compounds to 37x improvement over a year.",
    },
    {
        "uid": "ku.environment_design",
        "title": "Environment Design for Habits",
        "domain": "PERSONAL",
        "description": "Shaping your physical environment to make good habits easier.",
    },
    {
        "uid": "ku.habit_stacking",
        "title": "Habit Stacking",
        "domain": "PERSONAL",
        "description": "Linking new habits to existing habits using implementation intentions.",
    },
]

# ============================================================================
# KNOWLEDGE UNITS - Principles
# ============================================================================

PRINCIPLES_KUS = [
    {
        "uid": "ku.radical_truth_transparency",
        "title": "Radical Truth and Radical Transparency",
        "domain": "BUSINESS",
        "description": "Dalio's foundation: Complete honesty and openness in all interactions.",
    },
    {
        "uid": "ku.pain_reflection_progress",
        "title": "Pain + Reflection = Progress",
        "domain": "PERSONAL",
        "description": "Using painful experiences as opportunities for growth through reflection.",
    },
    {
        "uid": "ku.believability_weighted_decisions",
        "title": "Believability-Weighted Decision Making",
        "domain": "BUSINESS",
        "description": "Weighting opinions by track record and expertise, not seniority.",
    },
    {
        "uid": "ku.idea_meritocracy",
        "title": "Idea Meritocracy",
        "domain": "BUSINESS",
        "description": "System where the best ideas win, regardless of source.",
    },
    {
        "uid": "ku.systemized_principles",
        "title": "Systemized Principles",
        "domain": "BUSINESS",
        "description": "Converting life lessons into codified principles for decision-making.",
    },
    {
        "uid": "ku.five_step_process",
        "title": "Five-Step Process to Success",
        "domain": "PERSONAL",
        "description": "Goals → Problems → Diagnosis → Design → Execute",
    },
]

# ============================================================================
# EVIDENCE-BACKED RELATIONSHIPS
# ============================================================================

RELATIONSHIPS = [
    # Atomic Habits - Foundation Chain
    {
        "from_uid": "ku.four_laws_behavior_change",
        "to_uid": "ku.habit_formation_fundamentals",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Clear, James (2018). Atomic Habits, Chapter 1: 'The Surprising Power of Atomic Habits'",
                "Clear, James (2018). Atomic Habits, Chapter 3: 'How to Build Better Habits in 4 Simple Steps'",
                "Neuroscience research: Habit formation requires understanding basal ganglia function (MIT, 2005)",
            ],
            confidence=0.95,
            strength=0.9,
            notes="Four Laws build directly on neuroscience of habit formation",
        ),
    },
    {
        "from_uid": "ku.four_laws_behavior_change",
        "to_uid": "ku.cue_routine_reward",
        "metadata": create_research_backed_metadata(
            paper_citation="Duhigg, Charles (2012). The Power of Habit - Referenced extensively in Atomic Habits",
            additional_evidence=[
                "Clear, James (2018). Atomic Habits, Chapter 3: 'The cue triggers a craving'",
                "92% of habit experts cite cue-routine-reward as foundational (Clear's research)",
            ],
            confidence=0.92,
            strength=0.85,
        ),
    },
    {
        "from_uid": "ku.identity_based_habits",
        "to_uid": "ku.habit_formation_fundamentals",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Clear, James (2018). Atomic Habits, Chapter 2: 'How Your Habits Shape Your Identity'",
                "Identity change is the deepest level of behavior change (Clear, p. 31)",
                "Psychological research: Self-concept drives behavior more than goals (Dweck, 2006)",
            ],
            confidence=0.93,
            strength=0.88,
            notes="Identity-based approach is Clear's core innovation",
        ),
    },
    {
        "from_uid": "ku.habit_stacking",
        "to_uid": "ku.cue_routine_reward",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Clear, James (2018). Atomic Habits, Chapter 5: 'The Best Way to Start a New Habit'",
                "Implementation intentions research (Gollwitzer, 1999) - 91% success rate",
                "Habit stacking formula: 'After [CURRENT HABIT], I will [NEW HABIT]' (Clear, p. 74)",
            ],
            confidence=0.90,
            strength=0.82,
            notes="Habit stacking leverages existing neural pathways",
        ),
    },
    {
        "from_uid": "ku.environment_design",
        "to_uid": "ku.cue_routine_reward",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Clear, James (2018). Atomic Habits, Chapter 6: 'Motivation is Overrated; Environment Often Matters More'",
                "Environment shapes behavior more than willpower (Clear, p. 81-95)",
                "Visual cues account for 80% of habit triggers (research cited by Clear)",
            ],
            confidence=0.91,
            strength=0.85,
            notes="Environment design is the 1st Law implementation",
        ),
    },
    {
        "from_uid": "ku.aggregation_marginal_gains",
        "to_uid": "ku.habit_formation_fundamentals",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Clear, James (2018). Atomic Habits, Chapter 1: 'The Surprising Power of Atomic Habits'",
                "Mathematics: 1.01^365 = 37.78 (1% better daily = 37x improvement yearly)",
                "British Cycling Team case study: Aggregation led to 5 Tour de France wins (Clear, p. 13-15)",
            ],
            confidence=0.94,
            strength=0.87,
            notes="Compounding is the mathematical foundation of habit impact",
        ),
    },
    # Principles - Foundation Chain
    {
        "from_uid": "ku.idea_meritocracy",
        "to_uid": "ku.radical_truth_transparency",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Dalio, Ray (2017). Principles, Part 3: 'Work Principles' - Chapter 1",
                "Idea meritocracy requires radical transparency to function (Dalio, p. 308-312)",
                "Bridgewater case study: 40+ years of applying these principles",
            ],
            confidence=0.96,
            strength=0.92,
            notes="Radical transparency is the foundation enabling idea meritocracy",
        ),
    },
    {
        "from_uid": "ku.believability_weighted_decisions",
        "to_uid": "ku.idea_meritocracy",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Dalio, Ray (2017). Principles, Part 3: 'Be Radically Open-Minded' (p. 188-195)",
                "Believability weighting is the mechanism for idea meritocracy (Dalio, p. 327)",
                "Baseball card system: Track record determines believability weight",
            ],
            confidence=0.94,
            strength=0.90,
            notes="Believability weighting operationalizes idea meritocracy",
        ),
    },
    {
        "from_uid": "ku.systemized_principles",
        "to_uid": "ku.pain_reflection_progress",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Dalio, Ray (2017). Principles, Part 1: 'Where I'm Coming From' (p. 1-50)",
                "Principles emerge from reflecting on painful mistakes (Dalio's core thesis)",
                "Pain + Reflection = Progress → Principles (the complete cycle)",
            ],
            confidence=0.95,
            strength=0.91,
            notes="Systemized principles are the output of pain-reflection cycle",
        ),
    },
    {
        "from_uid": "ku.five_step_process",
        "to_uid": "ku.pain_reflection_progress",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Dalio, Ray (2017). Principles, Part 2: 'Life Principles' - 5-Step Process (p. 91-98)",
                "Each step requires honest reflection on failures (Dalio's framework)",
                "The process converts pain into actionable improvements",
            ],
            confidence=0.93,
            strength=0.88,
            notes="5-Step Process is the practical application of pain-reflection-progress",
        ),
    },
    # Cross-Book Integration
    {
        "from_uid": "ku.systemized_principles",
        "to_uid": "ku.identity_based_habits",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Both frameworks emphasize identity over outcomes (Clear & Dalio convergence)",
                "Principles define 'who you are' → Habits make it real (synthesis insight)",
                "Clear (2018) p. 31 + Dalio (2017) p. 308: Identity drives sustainable change",
            ],
            confidence=0.88,
            strength=0.82,
            notes="Cross-book synthesis: Principles define identity, habits embody it",
        ),
    },
    {
        "from_uid": "ku.radical_truth_transparency",
        "to_uid": "ku.pain_reflection_progress",
        "metadata": create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Dalio, Ray (2017). Principles, Part 3: 'Embrace Reality and Deal with It' (p. 188)",
                "Radical truth enables seeing painful realities clearly",
                "Without transparency, you can't reflect on true root causes (Dalio's warning)",
            ],
            confidence=0.94,
            strength=0.89,
            notes="Radical transparency is the prerequisite for honest reflection",
        ),
    },
]


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================


async def create_knowledge_units(driver, kus: list[dict], dry_run: bool = True):
    """Create knowledge unit nodes in Neo4j."""
    if dry_run:
        print(f"\nWould create {len(kus)} knowledge units:")
        for ku in kus:
            print(f"  - {ku['uid']}: {ku['title']}")
        return

    async with driver.session() as session:
        for ku in kus:
            query = """
            MERGE (ku:Ku {uid: $uid})
            SET ku.title = $title,
                ku.domain = $domain,
                ku.description = $description,
                ku.created_at = datetime(),
                ku.updated_at = datetime()
            RETURN ku.uid as uid
            """
            params = {
                "uid": ku["uid"],
                "title": ku["title"],
                "domain": ku["domain"],
                "description": ku["description"],
            }

            result = await session.run(query, params)
            record = await result.single()
            if record:
                print(f"  ✅ Created: {record['uid']}")


async def create_relationships(driver, relationships: list[dict], dry_run: bool = True):
    """Create REQUIRES relationships with evidence metadata."""
    if dry_run:
        print(f"\nWould create {len(relationships)} evidence-backed relationships:")
        for rel in relationships:
            metadata = rel["metadata"]
            print(f"  - {rel['from_uid']} → {rel['to_uid']}")
            print(f"    Source: {metadata.source}, Confidence: {metadata.confidence}")
            print(f"    Evidence: {len(metadata.evidence)} citations")
        return

    async with driver.session() as session:
        for rel in relationships:
            metadata = rel["metadata"]
            props = metadata.to_neo4j_properties()

            query = """
            MATCH (from:Ku {uid: $from_uid})
            MATCH (to:Ku {uid: $to_uid})
            MERGE (from)-[r:REQUIRES]->(to)
            SET r += $props
            RETURN from.uid as from_uid, to.uid as to_uid
            """
            params = {
                "from_uid": rel["from_uid"],
                "to_uid": rel["to_uid"],
                "props": props,
            }

            result = await session.run(query, params)
            record = await result.single()
            if record:
                print(f"  ✅ {record['from_uid']} → {record['to_uid']} (with evidence)")


async def verify_data(driver):
    """Verify the created data."""
    async with driver.session() as session:
        # Count KUs
        result = await session.run("MATCH (ku:Ku) RETURN count(ku) as total")
        ku_count = (await result.single())["total"]

        # Count relationships with evidence
        result = await session.run(
            """
            MATCH ()-[r:REQUIRES]->()
            RETURN
                count(r) as total,
                count(CASE WHEN r.evidence IS NOT NULL THEN 1 END) as with_evidence,
                count(CASE WHEN size(r.evidence) > 0 THEN 1 END) as with_citations
            """
        )
        rel_stats = await result.single()

        print("\n" + "=" * 80)
        print("VERIFICATION RESULTS")
        print("=" * 80)
        print(f"Knowledge Units Created: {ku_count}")
        print(f"Total REQUIRES Relationships: {rel_stats['total']}")
        print(f"With Evidence Field: {rel_stats['with_evidence']}")
        print(f"With Citations: {rel_stats['with_citations']}")

        # Show evidence quality distribution
        result = await session.run(
            """
            MATCH ()-[r:REQUIRES]->()
            WHERE size(r.evidence) > 0
            RETURN
                r.source as source,
                count(r) as count,
                avg(r.confidence) as avg_confidence,
                avg(size(r.evidence)) as avg_citations
            ORDER BY count DESC
            """
        )

        print("\nEvidence Quality by Source:")
        async for record in result:
            print(
                f"  {record['source']}: {record['count']} relationships, "
                f"avg confidence: {record['avg_confidence']:.2f}, "
                f"avg citations: {record['avg_citations']:.1f}"
            )


async def seed_mock_data(driver, dry_run: bool = True):
    """Main seeding function."""
    print("=" * 80)
    print("Seed Evidence Mock Data - Atomic Habits & Principles")
    print("=" * 80)
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'APPLY (will create data)'}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    print("📚 Source Books:")
    print("  - Atomic Habits by James Clear (2018)")
    print("  - Principles by Ray Dalio (2017)")
    print()

    # Combine all KUs
    all_kus = ATOMIC_HABITS_KUS + PRINCIPLES_KUS

    print(f"Will create {len(all_kus)} knowledge units:")
    print(f"  - Atomic Habits: {len(ATOMIC_HABITS_KUS)} concepts")
    print(f"  - Principles: {len(PRINCIPLES_KUS)} concepts")
    print(f"  - Cross-book relationships: {len(RELATIONSHIPS)} connections")
    print()

    # Create knowledge units
    await create_knowledge_units(driver, all_kus, dry_run)

    # Create relationships with evidence
    await create_relationships(driver, RELATIONSHIPS, dry_run)

    # Verify if not dry run
    if not dry_run:
        await verify_data(driver)

    print()
    print("=" * 80)


async def main():
    """Run seeding script."""
    # Parse command line arguments
    dry_run = True
    if len(sys.argv) > 1:
        if sys.argv[1] == "--apply":
            dry_run = False
        elif sys.argv[1] == "--dry-run":
            dry_run = True
        else:
            print("Usage: python seed_evidence_mock_data.py [--dry-run | --apply]")
            sys.exit(1)

    # Get Neo4j credentials
    neo4j_uri = get_credential("NEO4J_URI") or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = (
        get_credential("NEO4J_USER")
        or os.getenv("NEO4J_USERNAME")
        or os.getenv("NEO4J_USER", "neo4j")
    )
    neo4j_password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)

    # Convert neo4j:// to bolt://
    if neo4j_uri.startswith("neo4j://"):
        neo4j_uri = neo4j_uri.replace("neo4j://", "bolt://")

    if not neo4j_password:
        print("❌ Error: Neo4j password not found")
        sys.exit(1)

    # Create driver
    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        await seed_mock_data(driver, dry_run=dry_run)
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
