#!/usr/bin/env python3
"""
Test Events Intelligence Architecture
=====================================

Validates the Events intelligence pattern with:
- EventIntelligence tracking
- Event participation analysis
- Preparation level assessment
- Energy impact prediction
"""

import asyncio
import sys
from datetime import datetime

from core.models.event.event_intelligence import (
    EnergyImpact,
    EventIntelligence,
    EventParticipationContext,
    EventParticipationIntelligence,
    EventPreparationLevel,
)


async def test_events_intelligence():
    """Test the complete Events intelligence architecture"""
    print("🎯 Testing Events Intelligence Architecture")
    print("=" * 60)
    print("\n1. Testing EventIntelligence Entity")
    user_uid = "user_test_events"
    event_category = "professional_meetings"
    event_intelligence = EventIntelligence(
        uid=f"ei_{user_uid}_{event_category}",
        user_uid=user_uid,
        event_category=event_category,
        optimal_timing_patterns={
            "morning_start": 0.85,  # High effectiveness for morning meetings
            "afternoon_start": 0.65,
            "evening_start": 0.30,
            "duration_60min": 0.90,
            "duration_30min": 0.95,
            "duration_120min": 0.45,
        },
        participation_context_effectiveness={
            EventParticipationContext.IN_PERSON_FOCUSED: 0.90,
            EventParticipationContext.VIRTUAL_ENGAGED: 0.80,
            EventParticipationContext.HYBRID_BALANCED: 0.70,
            EventParticipationContext.PASSIVE_ATTENDANCE: 0.40,
        },
        energy_impact_patterns={
            "high_stakes_meeting": EnergyImpact.DRAINING,
            "routine_checkin": EnergyImpact.NEUTRAL,
            "creative_session": EnergyImpact.NEUTRAL,
            "team_celebration": EnergyImpact.ENERGIZING,
        },
        habit_reinforcement_effectiveness={"morning_reflection": 0.85, "focused_work_blocks": 0.75},
        goal_advancement_correlation={
            "improve_team_leadership": 0.80,
            "master_async_communication": 0.70,
        },
        learning_integration_patterns={
            "agile_methodology": ["sprint_planning", "retrospectives"],
            "team_dynamics": ["communication_patterns", "collaboration_methods"],
        },
    )
    print(f"✅ Created EventIntelligence: {event_intelligence.uid}")
    print(f"   Category: {event_intelligence.event_category}")
    print(f"   Learned patterns: {len(event_intelligence.optimal_timing_patterns)} timing insights")
    print("\n2. Testing Value Prediction")
    event_characteristics = {
        "timing": "morning_start",
        "duration": "duration_60min",
        "stakes": "high_stakes_meeting",
    }
    test_scenarios = [
        (EventPreparationLevel.THOROUGH, EventParticipationContext.IN_PERSON_FOCUSED),
        (EventPreparationLevel.ADEQUATE, EventParticipationContext.VIRTUAL_ENGAGED),
        (EventPreparationLevel.MINIMAL, EventParticipationContext.HYBRID_BALANCED),
        (EventPreparationLevel.NONE, EventParticipationContext.PASSIVE_ATTENDANCE),
    ]
    for prep_strategy, participation_context in test_scenarios:
        predicted_value = event_intelligence.predict_event_value(
            event_characteristics, prep_strategy, participation_context
        )
        print(f"   {prep_strategy.value} → {participation_context.value}: {predicted_value:.2f}")
    print("\n3. Testing Energy Management")
    current_energy = 0.75
    proposed_schedule = [
        {"type": "high_stakes_meeting", "duration": 60},
        {"type": "routine_checkin", "duration": 30},
        {"type": "creative_session", "duration": 90},
        {"type": "team_celebration", "duration": 45},
    ]
    energy_forecast = event_intelligence.predict_energy_impact(current_energy, proposed_schedule)
    print(f"   Current energy: {current_energy:.2f}")
    print(f"   Predicted final energy: {energy_forecast:.2f}")
    print(f"   Energy change: {energy_forecast - current_energy:+.2f}")
    print("\n4. Testing Preparation Strategy Optimization")
    available_prep_time = 120  # 2 hours
    event_importance = 0.9
    optimal_strategy = event_intelligence.optimize_preparation_strategy(
        available_prep_time, event_importance, event_characteristics
    )
    print(f"   Available time: {available_prep_time} minutes")
    print(f"   Event importance: {event_importance}")
    print(f"   Optimal strategy: {optimal_strategy.value}")
    print("\n5. Testing EventParticipationIntelligence")
    participation_intelligence = EventParticipationIntelligence(
        uid="epi_test_meeting_001",
        event_uid="event_team_standup_001",
        user_uid=user_uid,
        participated_at=datetime.now(),
        planned_duration=60,
        actual_duration=55,
        participation_context=EventParticipationContext.VIRTUAL_ENGAGED,
        preparation_time_minutes=45,
        preparation_level=EventPreparationLevel.ADEQUATE,
        value_realized=4,
        engagement_level=4,
        learning_gained=3,
        energy_impact=EnergyImpact.NEUTRAL,
        action_items_generated=[
            "Better async communication needed",
            "Sprint planning clarity improved",
        ],
        connections_made=2,
    )
    print(f"✅ Created EventParticipationIntelligence: {participation_intelligence.uid}")
    print(
        f"   Preparation effectiveness: {participation_intelligence.preparation_effectiveness():.2f}"
    )
    print(f"   Energy efficiency: {participation_intelligence.energy_efficiency():.2f}")
    print(f"   Learning value: {participation_intelligence.learning_value():.2f}")
    print("\n6. Testing Behavioral Pattern Recognition")
    patterns = participation_intelligence.extract_behavioral_patterns()
    for pattern_type, value in patterns.items():
        print(f"   {pattern_type}: {value}")
    print("\n7. Testing Cross-Domain Integration")
    cross_domain_context = {
        "active_habits": ["morning_reflection", "focused_work_blocks"],
        "current_goals": ["improve_team_leadership", "master_async_communication"],
        "knowledge_areas": ["agile_methodology", "team_dynamics"],
    }
    integration_insights = event_intelligence.analyze_cross_domain_synergies(cross_domain_context)
    print(f"   Cross-domain insights: {len(integration_insights)} synergies identified")
    for insight in integration_insights[:3]:  # Show first 3
        print(f"     • {insight}")
    print("\n8. Comprehensive Intelligence Validation")
    validation_results = {
        "entity_creation": event_intelligence.uid is not None,
        "value_prediction": all(
            0 <= predicted_value <= 1
            for predicted_value in [
                event_intelligence.predict_event_value(event_characteristics, prep, ctx)
                for prep, ctx in test_scenarios
            ]
        ),
        "energy_management": 0 <= energy_forecast <= 1,
        "preparation_optimization": optimal_strategy in EventPreparationLevel,
        "participation_tracking": participation_intelligence.uid is not None,
        "behavioral_analysis": len(patterns) > 0,
        "cross_domain_integration": len(integration_insights) > 0,
    }
    passed_tests = sum(validation_results.values())
    total_tests = len(validation_results)
    print(f"\n🎯 Events Intelligence Test Results: {passed_tests}/{total_tests} passed")
    for test_name, passed in validation_results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name}: {status}")
    if passed_tests == total_tests:
        print("\n🚀 Events Intelligence Architecture: FULLY OPERATIONAL")
        print("   Revolutionary transformation: Static calendar → Adaptive intelligence")
        print(
            "   The Events domain now learns from participation patterns and optimizes value realization"
        )
        return True
    else:
        print("\n⚠️  Events Intelligence Architecture: NEEDS ATTENTION")
        print(f"   {total_tests - passed_tests} tests failed - investigation required")
        return False


if __name__ == "__main__":
    print("Events Intelligence Architecture Validation")
    print("Testing revolutionary adaptive event management...")
    success = asyncio.run(test_events_intelligence())
    if success:
        print("\n🎉 EVENTS DOMAIN INTELLIGENCE ENHANCEMENT: COMPLETE")
        print("Ready to proceed to final domain (Principles) or deploy enhanced system")
    else:
        print("\n🔧 Further development needed before proceeding")
    sys.exit(0 if success else 1)
