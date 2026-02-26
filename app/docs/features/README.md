# SKUEL Features Documentation

This directory contains complete documentation for implemented features in SKUEL.

## What Goes Here

**Feature Documentation** includes:
- Complete feature overview
- Implementation details
- User workflows
- Architecture decisions
- Testing guidelines
- Migration notes (if applicable)

**Distinction from other docs**:
- **Features** = "What was built and how to use it"
- **Architecture** = "How the system is designed"
- **Patterns** = "Reusable implementation patterns"
- **Migrations** = "What changed and how to upgrade"

## Current Features

### SEL Adaptive Curriculum (February 2026)

**Document**: [SEL_ADAPTIVE_CURRICULUM.md](SEL_ADAPTIVE_CURRICULUM.md)

**Summary**: SEL (Social Emotional Learning) adaptive curriculum delivers personalized knowledge units across 5 core competencies. SEL navigation is a lens over the `/ku` hub.

---

## Future Features

Features planned or in development will be added here as they are implemented.

**Planned**:
- Advanced analytics dashboard (Q2 2026)
- Collaboration features (Q3 2026)
- Mobile app integration (Q4 2026)

---

## Contributing

When documenting a new feature:

1. **Create feature doc** in this directory (`FEATURE_NAME.md`)
2. **Include sections**:
   - Overview (what problem does it solve?)
   - Implementation (how was it built?)
   - Usage (how do users interact with it?)
   - Architecture (key design decisions)
   - Testing (how to verify it works)
   - Migration (if database/API changes)

3. **Update INDEX.md** to reference new doc
4. **Link related docs** (patterns, migrations, decisions)

**Template**: Use `SEL_ADAPTIVE_CURRICULUM.md` as a reference template.

---

**Last Updated**: January 31, 2026
