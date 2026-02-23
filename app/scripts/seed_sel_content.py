"""
Seed Script for SEL Knowledge Units
====================================

Creates example Social Emotional Learning knowledge units following Option B pattern:
- Separate KUs for each learning level
- ENABLES relationships link progression paths
- Prerequisites define dependencies

Usage:
    poetry run python scripts/seed_sel_content.py
"""

import asyncio
import os
from pathlib import Path

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from adapters.persistence.neo4j_adapter import Neo4jAdapter
from core.models.curriculum.curriculum import Curriculum
from core.models.entity import Entity
from core.models.enums import Domain, LearningLevel, SELCategory
from core.utils.logging import get_logger

# Add project root to path
project_root = Path(__file__).parent.parent


logger = get_logger(__name__)


# ============================================================================
# EXAMPLE SEL KNOWLEDGE UNITS
# ============================================================================

EXAMPLE_SEL_KUS = [
    # ==========================================================================
    # SELF-AWARENESS - Emotional Recognition Path
    # ==========================================================================
    {
        "uid": "ku.emotional_recognition.beginner",
        "title": "Understanding Your Emotions",
        "domain": Domain.KNOWLEDGE,
        "sel_category": SELCategory.SELF_AWARENESS,
        "learning_level": LearningLevel.BEGINNER,
        "estimated_time_minutes": 10,
        "difficulty_rating": 0.3,
        "content": """# Understanding Your Emotions

## Introduction
Emotions are signals that tell us about our internal state. Learning to identify and name emotions is the first step in emotional intelligence.

## The 5 Basic Emotions
1. **Joy** - Feeling happy, content, or pleased
2. **Sadness** - Feeling down, disappointed, or low
3. **Anger** - Feeling frustrated, annoyed, or upset
4. **Fear** - Feeling scared, anxious, or worried
5. **Surprise** - Feeling amazed, shocked, or caught off-guard

## Practice Exercise
Throughout today, pause 3 times and ask yourself: "What emotion am I feeling right now?"

Name it using one of the 5 basic emotions above.

## Why This Matters
When you can name your emotions, you gain power over them. Instead of being controlled by feelings, you can understand and manage them.

## Next Steps
Once you're comfortable identifying basic emotions, you'll learn to recognize emotional patterns and triggers.
""",
        "prerequisites": [],
        "enables": ["ku.emotional_recognition.intermediate"],
    },
    {
        "uid": "ku.emotional_recognition.intermediate",
        "title": "Emotional Patterns and Triggers",
        "domain": Domain.KNOWLEDGE,
        "sel_category": SELCategory.SELF_AWARENESS,
        "learning_level": LearningLevel.INTERMEDIATE,
        "estimated_time_minutes": 20,
        "difficulty_rating": 0.5,
        "content": """# Emotional Patterns and Triggers

## Building on Basics
Now that you know your basic emotions, let's explore what causes them and how they pattern over time.

## What Are Emotional Triggers?
Triggers are situations, people, or events that consistently provoke specific emotional responses.

### Common Triggers
- **Criticism** → Anger or sadness
- **Uncertainty** → Fear or anxiety
- **Success** → Joy or pride
- **Loss** → Sadness or grief

## Recognizing Your Patterns
Keep an emotion journal for 1 week:
- What emotion did you feel?
- What triggered it?
- How intense was it (1-10)?
- How long did it last?

## Pattern Analysis
After a week, look for:
1. Your most frequent emotions
2. Your common triggers
3. Times of day when certain emotions arise
4. People or situations that consistently affect you

## Why This Matters
Understanding your patterns gives you predictive power. You can anticipate emotional responses and prepare healthier reactions.

## Next Steps
Advanced emotional awareness involves understanding complex emotions and emotional regulation strategies.
""",
        "prerequisites": ["ku.emotional_recognition.beginner"],
        "enables": ["ku.emotional_recognition.advanced"],
    },
    {
        "uid": "ku.emotional_recognition.advanced",
        "title": "Complex Emotions and Regulation",
        "domain": Domain.KNOWLEDGE,
        "sel_category": SELCategory.SELF_AWARENESS,
        "learning_level": LearningLevel.ADVANCED,
        "estimated_time_minutes": 30,
        "difficulty_rating": 0.7,
        "content": """# Complex Emotions and Regulation

## Beyond Basic Emotions
Most adult emotions are blends of basic emotions with added context.

### Complex Emotions
- **Guilt** = Sadness + Self-blame
- **Shame** = Fear + Negative self-judgment
- **Pride** = Joy + Self-approval
- **Jealousy** = Fear + Anger + Sadness
- **Nostalgia** = Sadness + Joy (mixed)

## Emotional Regulation
Not suppressing emotions, but managing their expression and intensity.

### Regulation Strategies
1. **Cognitive Reappraisal** - Reframing the situation
2. **Mindful Acceptance** - Observing without judgment
3. **Expressive Writing** - Processing through journaling
4. **Physical Activity** - Using movement to shift state
5. **Social Support** - Talking with trusted others

## Advanced Practice
1. Identify a complex emotion you felt recently
2. Break it down into basic emotion components
3. Identify the trigger and your pattern
4. Choose one regulation strategy to apply next time

## Mastery
At this level, you can:
- Identify nuanced emotional states
- Predict your emotional responses
- Choose appropriate regulation strategies
- Explain your emotions to others clearly

## Integration
This knowledge enables effective self-management and healthier relationships.
""",
        "prerequisites": ["ku.emotional_recognition.intermediate"],
        "enables": [],
    },
    # ==========================================================================
    # SELF-MANAGEMENT - Goal Setting Path
    # ==========================================================================
    {
        "uid": "ku.goal_setting.beginner",
        "title": "Setting Your First Goal",
        "domain": Domain.KNOWLEDGE,
        "sel_category": SELCategory.SELF_MANAGEMENT,
        "learning_level": LearningLevel.BEGINNER,
        "estimated_time_minutes": 15,
        "difficulty_rating": 0.3,
        "content": """# Setting Your First Goal

## What Is a Goal?
A goal is a specific outcome you want to achieve. It gives direction to your actions and motivation to your days.

## Why Set Goals?
Without goals:
- Days feel aimless
- Progress is invisible
- Motivation wavers

With goals:
- You know what to work toward
- You can measure progress
- You feel accomplished

## Your First Goal
Start small and specific:

❌ Bad: "Be healthier"
✅ Good: "Walk 10 minutes every morning this week"

❌ Bad: "Learn programming"
✅ Good: "Complete one Python tutorial by Friday"

## The Key Elements
1. **Specific** - Exactly what will you do?
2. **Measurable** - How will you know you did it?
3. **Time-bound** - By when?

## Practice Exercise
Write down ONE small goal for this week:
- Make it specific
- Make it measurable
- Set a deadline

Example: "Read 10 pages of my book every evening before bed this week"

## Next Steps
Once you've achieved your first small goal, you'll learn how to set and track bigger goals using the SMART framework.
""",
        "prerequisites": [],
        "enables": ["ku.goal_setting.intermediate"],
    },
    {
        "uid": "ku.goal_setting.intermediate",
        "title": "SMART Goals Framework",
        "domain": Domain.KNOWLEDGE,
        "sel_category": SELCategory.SELF_MANAGEMENT,
        "learning_level": LearningLevel.INTERMEDIATE,
        "estimated_time_minutes": 25,
        "difficulty_rating": 0.5,
        "content": """# SMART Goals Framework

## Building on Your Success
You've set and achieved small goals. Now let's scale up with the SMART framework.

## SMART Criteria
**S**pecific - What exactly will you accomplish?
**M**easurable - How will you track progress?
**A**chievable - Is it realistic given your resources?
**R**elevant - Does it align with your values?
**T**ime-bound - What's the deadline?

## Example Transformation
**Vague goal**: "Get better at my job"

**SMART goal**: "Complete the advanced Excel course and apply 3 new techniques in my monthly reports by the end of next quarter"
- Specific: Advanced Excel course, 3 techniques, monthly reports
- Measurable: Course completion, 3 techniques used
- Achievable: Quarter is enough time
- Relevant: Improves job performance
- Time-bound: End of quarter

## Breaking Down Goals
Big goals need sub-goals:

**3-month goal**: Run a 5K race
**Monthly milestones**:
- Month 1: Run 1 mile without stopping
- Month 2: Run 2 miles comfortably
- Month 3: Complete 3 miles (5K)

**Weekly actions**:
- Week 1-4: Run 3 times per week, gradually increasing distance

## Practice Exercise
Take a goal you care about and make it SMART:
1. Write your vague goal
2. Apply each SMART criterion
3. Break it into monthly milestones
4. Define weekly actions

## Tracking Progress
- Use SKUEL's goal system to track
- Review weekly: Are you on track?
- Adjust if needed - goals aren't rigid

## Next Steps
Advanced goal-setting involves long-term vision planning and integrating multiple life domains.
""",
        "prerequisites": ["ku.goal_setting.beginner"],
        "enables": ["ku.goal_setting.advanced"],
    },
    {
        "uid": "ku.goal_setting.advanced",
        "title": "Long-Term Vision and Life Goals",
        "domain": Domain.KNOWLEDGE,
        "sel_category": SELCategory.SELF_MANAGEMENT,
        "learning_level": LearningLevel.ADVANCED,
        "estimated_time_minutes": 40,
        "difficulty_rating": 0.7,
        "content": """# Long-Term Vision and Life Goals

## From Tactics to Strategy
You've mastered SMART goals for specific outcomes. Now let's integrate goals into a coherent life vision.

## The Vision Pyramid
**Vision (10+ years)** - Your life direction
**Long-term goals (3-5 years)** - Major milestones
**Annual goals (1 year)** - This year's focus
**Quarterly goals (3 months)** - Current priorities
**Weekly actions** - What you do this week

## Creating Your Vision
Ask yourself:
1. What do you want your life to look like in 10 years?
2. What would you regret NOT doing?
3. What impact do you want to make?
4. Who do you want to become?

Write a vision statement: "In 10 years, I want to..."

## Balanced Life Domains
Set goals across multiple domains:
- **Career/Professional** - Work and skill development
- **Financial** - Money and resources
- **Health/Physical** - Body and energy
- **Relationships** - Family and friends
- **Personal Growth** - Learning and character
- **Contribution** - Service and impact

## Working Backwards
From your 10-year vision:
1. What must happen in 5 years?
2. What must happen in 3 years?
3. What must happen in 1 year?
4. What must happen this quarter?

## Goal Integration
Advanced goals support each other:
- Learning Spanish (growth) → Better career opportunities (professional)
- Morning exercise (health) → More energy (all domains benefit)

## Review Cadence
- **Weekly**: Review weekly actions, adjust as needed
- **Monthly**: Check monthly milestones
- **Quarterly**: Assess quarterly goals, plan next quarter
- **Annually**: Major reflection and vision update

## Practice Exercise
1. Write your 10-year vision statement
2. Identify 3-5 long-term goals (3-5 years) that support it
3. Define THIS year's goals for each long-term goal
4. Set THIS quarter's specific goals

## Mastery
You now have:
- A clear vision for your life
- Integrated goals across domains
- A system for breaking big dreams into actions
- Regular review rhythms

This is self-management at the highest level.
""",
        "prerequisites": ["ku.goal_setting.intermediate"],
        "enables": [],
    },
    # ==========================================================================
    # RESPONSIBLE DECISION-MAKING - Choice Framework Path
    # ==========================================================================
    {
        "uid": "ku.decision_framework.beginner",
        "title": "Making Simple Choices",
        "domain": Domain.KNOWLEDGE,
        "sel_category": SELCategory.RESPONSIBLE_DECISION_MAKING,
        "learning_level": LearningLevel.BEGINNER,
        "estimated_time_minutes": 12,
        "difficulty_rating": 0.4,
        "content": """# Making Simple Choices

## Every Day, Dozens of Choices
From what to eat for breakfast to how to respond to a text message, we make countless decisions daily.

## Why Decision-Making Matters
Good choices compound over time:
- Eating healthy → Better energy → More productivity → Better outcomes
- Poor choices also compound:
- Staying up late → Tired next day → Poor performance → Stress

## A Simple Framework
For everyday decisions, ask 3 questions:

### 1. What are my options?
List 2-3 possible choices clearly.

### 2. What are the immediate consequences?
For each option, what happens right away?

### 3. Which aligns with my goals?
Which choice moves me toward what I want?

## Example: Should I watch TV or read tonight?

**Options**:
- Watch TV for 2 hours
- Read for 30 minutes, then watch TV

**Immediate consequences**:
- TV: Entertainment, relaxation, but no progress on reading goal
- Read then TV: Progress on goal + some relaxation

**Alignment**:
My goal is to read more. Reading 30 min aligns better.

**Decision**: Read for 30 minutes first

## Practice Exercise
Next time you face a choice today:
1. Pause and identify your options
2. Consider immediate consequences
3. Choose what aligns with your goals

## Common Traps
- **Autopilot**: Making choices without thinking
- **Impulse**: Choosing based on immediate feelings only
- **Avoidance**: Not deciding is also a decision

## Next Steps
For bigger decisions, you'll learn to evaluate long-term consequences and ethical considerations.
""",
        "prerequisites": [],
        "enables": ["ku.decision_framework.intermediate"],
    },
    {
        "uid": "ku.decision_framework.intermediate",
        "title": "Evaluating Consequences",
        "domain": Domain.KNOWLEDGE,
        "sel_category": SELCategory.RESPONSIBLE_DECISION_MAKING,
        "learning_level": LearningLevel.INTERMEDIATE,
        "estimated_time_minutes": 20,
        "difficulty_rating": 0.6,
        "content": """# Evaluating Consequences

## Beyond Immediate Effects
Simple choices focus on immediate consequences. Important decisions require looking further ahead.

## Time Horizons
Evaluate consequences across 3 time horizons:

### Immediate (Hours/Days)
- How do I feel right now?
- What happens today?

### Short-term (Weeks/Months)
- How does this affect my next month?
- What patterns does this create?

### Long-term (Years)
- Where does this path lead?
- Who do I become if I choose this?

## Example: Job Offer Decision

**Option A: Higher paying job, longer commute**
- Immediate: Excitement, more money
- Short-term: Tired from commute, less time with family
- Long-term: Better resume, but strained relationships?

**Option B: Lower pay, work from home**
- Immediate: Disappointment about pay
- Short-term: More family time, better work-life balance
- Long-term: Stronger relationships, maybe slower career growth

## The Second-Order Effect
Every choice creates ripples:

First-order: "I'll skip the gym today" → More time now
Second-order: Start skipping regularly → Lose fitness
Third-order: Lower energy → Reduced productivity → Less success

## Decision Matrix
For important choices, score each option:

| Factor | Weight | Option A | Option B |
|--------|--------|----------|----------|
| Aligns with values | 10 | 7 | 9 |
| Financial impact | 8 | 9 | 6 |
| Time cost | 7 | 4 | 8 |
| Relationships | 9 | 5 | 9 |
| Growth potential | 8 | 8 | 7 |

Multiply weight × score, sum for each option.

## Practice Exercise
Think of a decision you're facing:
1. List your options (2-3)
2. For each, write consequences across 3 time horizons
3. Create a simple decision matrix
4. Which option scores highest?

## Considering Others
Responsible decisions consider:
- How does this affect others?
- Is this fair?
- Would I want others to make this choice?

## Next Steps
Advanced decision-making involves ethical reasoning and complex trade-offs.
""",
        "prerequisites": ["ku.decision_framework.beginner"],
        "enables": ["ku.decision_framework.advanced"],
    },
    # ==========================================================================
    # SOCIAL AWARENESS - Empathy Development Path
    # ==========================================================================
    {
        "uid": "ku.empathy_development.beginner",
        "title": "Understanding Others' Feelings",
        "domain": Domain.KNOWLEDGE,
        "sel_category": SELCategory.SOCIAL_AWARENESS,
        "learning_level": LearningLevel.BEGINNER,
        "estimated_time_minutes": 15,
        "difficulty_rating": 0.4,
        "content": """# Understanding Others' Feelings

## What Is Empathy?
Empathy is the ability to understand and share the feelings of another person.

## Why Empathy Matters
- Stronger relationships
- Better communication
- Less conflict
- More support when others need it

## The Two Types
**Cognitive Empathy**: Understanding what someone thinks/feels
**Emotional Empathy**: Actually feeling what they feel

We'll focus on cognitive empathy first.

## How to Practice
### 1. Pay Attention
- Watch body language
- Listen to tone of voice
- Notice facial expressions

### 2. Ask Yourself
"If I were in their situation, what would I be feeling?"

### 3. Validate
You don't have to agree, just acknowledge their feelings.

"I can see you're frustrated" vs. "You shouldn't feel that way"

## Common Emotional Cues
- **Crossed arms** → Defensive or closed off
- **Avoiding eye contact** → Uncomfortable or anxious
- **Raised voice** → Angry or excited
- **Slow speech** → Sad or tired
- **Fidgeting** → Nervous or impatient

## Practice Exercise
Today, have a conversation where you:
1. Focus completely on the other person
2. Try to identify what they're feeling
3. Validate their emotion (even if you disagree with their view)

Example: "It sounds like you're really excited about this opportunity"

## Next Steps
Intermediate empathy involves perspective-taking and understanding different viewpoints.
""",
        "prerequisites": [],
        "enables": ["ku.empathy_development.intermediate"],
    },
    # ==========================================================================
    # RELATIONSHIP SKILLS - Communication Path
    # ==========================================================================
    {
        "uid": "ku.communication.beginner",
        "title": "Clear Communication Basics",
        "domain": Domain.KNOWLEDGE,
        "sel_category": SELCategory.RELATIONSHIP_SKILLS,
        "learning_level": LearningLevel.BEGINNER,
        "estimated_time_minutes": 15,
        "difficulty_rating": 0.3,
        "content": """# Clear Communication Basics

## Communication Is a Skill
Most conflicts and misunderstandings come from poor communication, not bad intentions.

## The Two Sides
1. **Expressing Yourself** - Saying what you mean clearly
2. **Active Listening** - Truly hearing others

## Expressing Yourself Clearly
### Use "I" Statements
Instead of blaming, share your experience:

❌ "You never listen to me"
✅ "I feel unheard when I'm interrupted"

❌ "You're always late"
✅ "I feel frustrated when meetings start late"

### Be Specific
Vague communication creates confusion:

❌ "We need to talk about our relationship"
✅ "I'd like to discuss how we're dividing household chores"

## Active Listening
### The 3 Steps
1. **Listen without interrupting** - Let them finish
2. **Reflect back** - "What I'm hearing is..."
3. **Ask clarifying questions** - "Can you tell me more about..."

### What NOT to Do
- Interrupt with your own story
- Immediately offer solutions
- Check your phone
- Think about your response while they're talking

## Practice Exercise
In your next conversation:
1. Use one "I" statement to express a feeling
2. Practice reflecting back what you heard
3. Ask one clarifying question before responding

## Example Dialogue
Person A: "I'm really stressed about this project"
You: "It sounds like you're feeling overwhelmed by the project. What's the most stressful part?"

## Next Steps
Intermediate communication covers difficult conversations and conflict resolution.
""",
        "prerequisites": [],
        "enables": ["ku.communication.intermediate"],
    },
]


# ============================================================================
# SEED FUNCTIONS
# ============================================================================


async def seed_sel_content(ku_backend):
    """
    Seed example SEL knowledge units into the database.

    Args:
        ku_backend: UniversalNeo4jBackend[Ku] for creating KUs

    Returns:
        Number of KUs created
    """
    created_count = 0

    logger.info("=" * 70)
    logger.info("SEEDING SEL KNOWLEDGE UNITS")
    logger.info("=" * 70)

    for ku_data in EXAMPLE_SEL_KUS:
        try:
            # Create Ku object (prerequisites and enables are graph relationships, not fields)
            content_body = ku_data.get("content", "")
            ku = Curriculum(
                uid=ku_data["uid"],
                title=ku_data["title"],
                domain=ku_data["domain"],
                sel_category=ku_data["sel_category"],
                learning_level=ku_data["learning_level"],
                estimated_time_minutes=ku_data["estimated_time_minutes"],
                difficulty_rating=ku_data["difficulty_rating"],
                word_count=len(content_body.split()) if content_body else 0,
            )

            # Create in database
            result = await ku_backend.create(ku)

            if result.is_ok:
                logger.info(f"✅ Created: {ku.uid}")
                logger.info(f"   Title: {ku.title}")
                logger.info(f"   Category: {ku.sel_category.value if ku.sel_category else 'None'}")
                logger.info(f"   Level: {ku.learning_level.value}")
                created_count += 1
            else:
                logger.error(f"❌ Failed to create {ku.uid}: {result.error}")

        except Exception as e:
            logger.error(f"❌ Error creating {ku_data['uid']}: {e}")

    logger.info("=" * 70)
    logger.info(f"CREATED {created_count} / {len(EXAMPLE_SEL_KUS)} KNOWLEDGE UNITS")
    logger.info("=" * 70)

    return created_count


async def create_enables_relationships(driver):
    """
    Create ENABLES relationships between KUs based on the enables field.

    Args:
        driver: Neo4j driver instance

    Returns:
        Number of relationships created
    """
    logger.info("=" * 70)
    logger.info("CREATING ENABLES RELATIONSHIPS")
    logger.info("=" * 70)

    created_count = 0

    async with driver.session() as session:
        for ku_data in EXAMPLE_SEL_KUS:
            uid = ku_data["uid"]
            enables_list = ku_data.get("enables", [])

            for target_uid in enables_list:
                try:
                    # Create ENABLES relationship
                    query = """
                    MATCH (source:Entity {uid: $source_uid})
                    MATCH (target:Entity {uid: $target_uid})
                    MERGE (source)-[r:ENABLES]->(target)
                    RETURN r
                    """

                    result = await session.run(query, source_uid=uid, target_uid=target_uid)

                    records = [record async for record in result]

                    if records:
                        logger.info(f"✅ Created ENABLES: {uid} → {target_uid}")
                        created_count += 1
                    else:
                        logger.warning(f"⚠️  Could not create ENABLES: {uid} → {target_uid}")

                except Exception as e:
                    logger.error(f"❌ Error creating relationship {uid} → {target_uid}: {e}")

    logger.info("=" * 70)
    logger.info(f"CREATED {created_count} ENABLES RELATIONSHIPS")
    logger.info("=" * 70)

    return created_count


async def main():
    """Main execution function"""
    logger.info("Starting SEL content seeding...")

    # Get Neo4j connection details from environment
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    # Connect to Neo4j
    try:
        adapter = Neo4jAdapter(neo4j_uri, neo4j_user, neo4j_password)
        await adapter.connect()
        logger.info(f"✅ Connected to Neo4j at {neo4j_uri}")

        # Get driver for direct queries
        driver = adapter.get_driver()

        # Create backend for Knowledge
        ku_backend = UniversalNeo4jBackend[Entity](driver, "Curriculum", Entity)

        # Seed KUs
        ku_count = await seed_sel_content(ku_backend)

        # Create relationships
        rel_count = await create_enables_relationships(driver)

        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("SEEDING COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Knowledge Units: {ku_count}")
        logger.info(f"ENABLES Relationships: {rel_count}")
        logger.info("=" * 70)

        # Close connection
        await adapter.close()
        logger.info("✅ Closed Neo4j connection")

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
