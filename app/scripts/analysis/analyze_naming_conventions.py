#!/usr/bin/env python3
"""
Naming Convention Analysis for Auto-Generation
==============================================

Analyze all domain models and backends to determine if naming conventions
are consistent enough for convention-based auto-generation.
"""

import re
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent


class NamingConventionAnalyzer:
    def __init__(self) -> None:
        self.findings = {
            "pure_models": {},
            "dto_models": {},
            "request_models": {},
            "backends": {},
            "services": {},
            "inconsistencies": [],
            "patterns": {},
        }

    def analyze_directory_structure(self):
        """Analyze the directory structure for consistency."""
        print("🏗️  ANALYZING DIRECTORY STRUCTURE")
        print("=" * 50)

        models_dir = Path("core/models")

        domains = [
            domain_dir.name
            for domain_dir in models_dir.iterdir()
            if domain_dir.is_dir() and not domain_dir.name.startswith("__")
        ]

        print(f"📁 Found {len(domains)} domain directories:")
        for domain in sorted(domains):
            print(f"   • {domain}/")

        return domains

    def analyze_pure_models(self, domains: list[str]):
        """Analyze Pure model naming patterns."""
        print("\n🔍 ANALYZING PURE MODELS")
        print("=" * 50)

        patterns = {}
        inconsistencies = []

        for domain in domains:
            domain_path = Path(f"core/models/{domain}")

            # Look for pure model files
            pure_files = []
            for pattern in ["*_pure.py", f"{domain}.py"]:
                pure_files.extend(domain_path.glob(pattern))

            if pure_files:
                for file in pure_files:
                    # Try to extract class names
                    try:
                        content = file.read_text()

                        # Find dataclass definitions
                        classes = re.findall(r"@dataclass.*?\nclass (\w+):", content, re.DOTALL)

                        if classes:
                            patterns[domain] = {
                                "file": file.name,
                                "classes": classes,
                                "primary_class": self._identify_primary_class(classes, domain),
                            }

                            print(f"✅ {domain:12} → {file.name:20} → {classes}")
                        else:
                            inconsistencies.append(f"No dataclasses found in {file}")

                    except Exception as e:
                        inconsistencies.append(f"Error reading {file}: {e}")
            else:
                inconsistencies.append(f"No pure model file found for domain: {domain}")
                print(f"❌ {domain:12} → No pure model file found")

        self.findings["pure_models"] = patterns
        self.findings["inconsistencies"].extend(inconsistencies)

        return patterns

    def _identify_primary_class(self, classes: list[str], domain: str) -> str:
        """Identify the primary class for a domain."""
        # Look for patterns: DomainPure, Domain, or first class
        domain_capitalized = domain.capitalize()

        for cls in classes:
            if cls == f"{domain_capitalized}Pure" or cls == domain_capitalized:
                return cls

        # Return first class as fallback
        return classes[0] if classes else None

    def analyze_backends(self):
        """Analyze backend naming patterns."""
        print("\n🔧 ANALYZING BACKEND PATTERNS")
        print("=" * 50)

        backends_dir = Path("adapters/persistence/neo4j")
        backend_files = list(backends_dir.glob("*_neo4j_backend.py"))

        patterns = {}

        for file in backend_files:
            domain = file.name.replace("_neo4j_backend.py", "")

            try:
                content = file.read_text()

                # Find class definitions
                classes = re.findall(r"class (\w+)\(.*?\):", content)

                patterns[domain] = {"file": file.name, "classes": classes}

                print(f"✅ {domain:12} → {file.name:30} → {classes}")

            except Exception as e:
                self.findings["inconsistencies"].append(f"Error reading {file}: {e}")

        self.findings["backends"] = patterns
        return patterns

    def analyze_services(self):
        """Analyze service naming patterns."""
        print("\n⚙️  ANALYZING SERVICE PATTERNS")
        print("=" * 50)

        services_dir = Path("core/services")
        service_files = list(services_dir.glob("*_service.py"))

        patterns = {}

        for file in service_files:
            service_name = file.name.replace("_service.py", "")

            try:
                content = file.read_text()

                # Find class definitions
                classes = re.findall(r"class (\w+Service[^(]*)\(.*?\):", content)

                if classes:
                    patterns[service_name] = {"file": file.name, "classes": classes}

                    print(f"✅ {service_name:15} → {file.name:25} → {classes}")

            except Exception as e:
                self.findings["inconsistencies"].append(f"Error reading {file}: {e}")

        self.findings["services"] = patterns
        return patterns

    def analyze_label_patterns(self, pure_patterns: dict[str, Any]):
        """Analyze Neo4j label patterns."""
        print("\n🏷️  ANALYZING NEO4J LABEL PATTERNS")
        print("=" * 50)

        label_mappings = {}

        for domain, pattern in pure_patterns.items():
            primary_class = pattern.get("primary_class", "")

            # Infer Neo4j label from class name (remove "Pure" suffix if present)
            label = primary_class.removesuffix("Pure")

            label_mappings[domain] = {
                "class": primary_class,
                "inferred_label": label,
                "domain": domain,
            }

            print(f"✅ {domain:12} → {primary_class:15} → Neo4j:{label}")

        self.findings["patterns"]["labels"] = label_mappings
        return label_mappings

    def evaluate_convention_strength(self):
        """Evaluate if conventions are strong enough for auto-generation."""
        print("\n🎯 CONVENTION STRENGTH EVALUATION")
        print("=" * 50)

        score = 0
        max_score = 0
        issues = []

        # 1. Directory structure consistency (20 points)
        max_score += 20
        domains = list(self.findings["pure_models"].keys())
        if len(domains) >= 8:  # We expect at least 8 domains
            score += 20
            print("✅ Directory structure: EXCELLENT (20/20)")
        else:
            score += 10
            print("⚠️  Directory structure: PARTIAL (10/20)")
            issues.append("Some domains missing proper directory structure")

        # 2. Pure model consistency (30 points)
        max_score += 30
        pure_models = self.findings["pure_models"]
        consistent_models = 0

        for pattern in pure_models.values():
            if pattern.get("primary_class") and pattern["primary_class"].endswith("Pure"):
                consistent_models += 1

        consistency_ratio = consistent_models / len(pure_models) if pure_models else 0
        pure_score = int(30 * consistency_ratio)
        score += pure_score
        print(f"✅ Pure model naming: {consistency_ratio:.1%} consistent ({pure_score}/30)")

        if consistency_ratio < 0.8:
            issues.append("Pure model naming not sufficiently consistent")

        # 3. Backend consistency (25 points)
        max_score += 25
        backends = self.findings["backends"]
        backend_score = min(25, len(backends) * 3)  # 3 points per backend, max 25
        score += backend_score
        print(f"✅ Backend coverage: {len(backends)} backends ({backend_score}/25)")

        # 4. Label inference reliability (25 points)
        max_score += 25
        labels = self.findings["patterns"].get("labels", {})
        reliable_labels = 0

        for mapping in labels.values():
            inferred = mapping["inferred_label"]
            if inferred and inferred.isalpha() and inferred[0].isupper():
                reliable_labels += 1

        label_ratio = reliable_labels / len(labels) if labels else 0
        label_score = int(25 * label_ratio)
        score += label_score
        print(f"✅ Label inference: {label_ratio:.1%} reliable ({label_score}/25)")

        # Overall score
        percentage = (score / max_score) * 100
        print(f"\n📊 OVERALL CONVENTION STRENGTH: {score}/{max_score} ({percentage:.0f}%)")

        if percentage >= 80:
            print("🟢 EXCELLENT - Ready for convention-based auto-generation")
            recommendation = "PROCEED_WITH_CONVENTION"
        elif percentage >= 60:
            print("🟡 GOOD - Convention-based possible with minor fixes")
            recommendation = "FIX_THEN_CONVENTION"
        else:
            print("🔴 NEEDS WORK - Manual migration recommended first")
            recommendation = "MANUAL_FIRST"

        return {
            "score": score,
            "max_score": max_score,
            "percentage": percentage,
            "recommendation": recommendation,
            "issues": issues,
        }

    def generate_convention_based_factory(self):
        """Generate a convention-based factory based on discovered patterns."""
        print("\n🏭 CONVENTION-BASED FACTORY GENERATOR")
        print("=" * 50)

        pure_models = self.findings["pure_models"]
        labels = self.findings["patterns"].get("labels", {})

        factory_code = '''"""
Auto-Generated Convention-Based Backend Factory
==============================================

Generated from naming convention analysis.
Creates universal backends automatically based on domain naming patterns.
"""


T = TypeVar('T')

# Auto-discovered domain mappings
DOMAIN_MAPPINGS = {
'''

        for domain, label_info in labels.items():
            pure_class = label_info["class"]
            neo4j_label = label_info["inferred_label"]

            # Generate import path
            import_path = f"core.models.{domain}"
            if domain in pure_models:
                file_name = pure_models[domain]["file"]
                if file_name != f"{domain}.py":
                    # Adjust import path for non-standard file names
                    module_name = file_name.replace(".py", "")
                    import_path = f"core.models.{domain}.{module_name}"

            factory_code += f'''    "{domain}": {{
        "class": "{pure_class}",
        "label": "{neo4j_label}",
        "import": "{import_path}"
    }},
'''

        factory_code += '''}

class ConventionBasedFactory:
    """Auto-generates backends based on naming conventions."""

    @staticmethod
    def create_backend(domain: str, driver: AsyncDriver) -> UniversalNeo4jBackend:
        """Create universal backend for any domain by convention."""
        if domain not in DOMAIN_MAPPINGS:
            raise ValueError(f"Unknown domain: {domain}. Available: {list(DOMAIN_MAPPINGS.keys())}")

        mapping = DOMAIN_MAPPINGS[domain]

        # Dynamic import
        module = importlib.import_module(mapping["import"])
        entity_class = getattr(module, mapping["class"])

        return UniversalNeo4jBackend(
            driver=driver,
            label=mapping["label"],
            entity_class=entity_class
        )

    @staticmethod
    def create_all_backends(driver: AsyncDriver) -> Dict[str, UniversalNeo4jBackend]:
        """Create all backends at once."""
        return {
            domain: ConventionBasedFactory.create_backend(domain, driver)
            for domain in DOMAIN_MAPPINGS.keys()
        }

# Convenience functions
def create_tasks_backend(driver: AsyncDriver) -> UniversalNeo4jBackend:
    return ConventionBasedFactory.create_backend("task", driver)

def create_events_backend(driver: AsyncDriver) -> UniversalNeo4jBackend:
    return ConventionBasedFactory.create_backend("event", driver)

# Add more convenience functions for each domain...
'''

        return factory_code

    def run_analysis(self):
        """Run complete naming convention analysis."""
        print("🔍 NAMING CONVENTION ANALYSIS FOR AUTO-GENERATION")
        print("=" * 60)

        # 1. Analyze directory structure
        domains = self.analyze_directory_structure()

        # 2. Analyze pure models
        pure_patterns = self.analyze_pure_models(domains)

        # 3. Analyze backends
        self.analyze_backends()

        # 4. Analyze services
        self.analyze_services()

        # 5. Analyze label patterns
        self.analyze_label_patterns(pure_patterns)

        # 6. Evaluate convention strength
        evaluation = self.evaluate_convention_strength()

        # 7. Report inconsistencies
        if self.findings["inconsistencies"]:
            print(f"\n⚠️  INCONSISTENCIES FOUND ({len(self.findings['inconsistencies'])})")
            print("=" * 50)
            for issue in self.findings["inconsistencies"]:
                print(f"• {issue}")

        # 8. Generate factory if conventions are strong enough
        if evaluation["percentage"] >= 60:
            print("\n🏭 GENERATING CONVENTION-BASED FACTORY")
            print("=" * 50)
            factory_code = self.generate_convention_based_factory()

            # Save factory code
            with Path("convention_based_factory.py").open("w") as f:
                f.write(factory_code)
            print("✅ Factory code generated: convention_based_factory.py")

        return evaluation


if __name__ == "__main__":
    analyzer = NamingConventionAnalyzer()
    evaluation = analyzer.run_analysis()

    print(f"\n🎯 RECOMMENDATION: {evaluation['recommendation']}")
    print("=" * 60)

    if evaluation["recommendation"] == "PROCEED_WITH_CONVENTION":
        print("✅ Your naming conventions are excellent!")
        print("✅ Convention-based auto-generation is ready to implement")
        print("✅ Proceed with full convention-based migration")
    elif evaluation["recommendation"] == "FIX_THEN_CONVENTION":
        print("⚠️  Your naming conventions are mostly good")
        print("⚠️  Fix the identified issues first, then proceed with convention-based migration")
        print("⚠️  Alternatively, start with manual migration for complex domains")
    else:
        print("🔴 Your naming conventions need strengthening")
        print("🔴 Recommend manual migration first to establish consistent patterns")
        print("🔴 Then transition to convention-based approach")
