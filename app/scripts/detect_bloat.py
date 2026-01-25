#!/usr/bin/env python3
"""
Bloat Detection Script
======================

Systematically finds unused code in the SKUEL codebase:
- Unused events (defined but never published)
- Unused methods (defined but never called)
- Unused service methods (public methods never called externally)
- Dead event subscribers (subscribed but event never published)

Usage:
    poetry run python scripts/detect_bloat.py
    poetry run python scripts/detect_bloat.py --events-only
    poetry run python scripts/detect_bloat.py --methods-only
    poetry run python scripts/detect_bloat.py --verbose
"""

import argparse
import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

# ANSI colors for terminal output
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


class BloatDetector:
    """Detects unused code patterns across the codebase."""

    def __init__(self, root_dir: Path, verbose: bool = False):
        self.root_dir = root_dir
        self.verbose = verbose

        # Event tracking
        self.event_definitions: dict[str, list[str]] = defaultdict(list)  # event_class -> [files]
        self.event_publications: dict[str, list[str]] = defaultdict(list)  # event_class -> [files]
        self.event_subscriptions: dict[str, list[str]] = defaultdict(list)  # event_class -> [files]
        self.event_imports: dict[str, list[str]] = defaultdict(list)  # NEW: event_class -> [files]

        # Method tracking
        self.method_definitions: dict[str, list[str]] = defaultdict(list)  # method_name -> [files]
        self.method_calls: dict[str, list[str]] = defaultdict(list)  # method_name -> [files]
        self.reflection_calls: dict[str, list[str]] = defaultdict(list)  # NEW: method_name -> [files using reflection]

        # Service method tracking (public methods in services)
        self.service_methods: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )  # service_name -> method_name -> [files where defined]
        self.service_method_calls: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )  # service_name -> method_name -> [files where called]

    def scan_codebase(self) -> None:
        """Scan entire codebase for events and methods."""
        print(f"{CYAN}🔍 Scanning codebase for bloat...{RESET}\n")

        # Scan core directory
        core_dir = self.root_dir / "core"
        if core_dir.exists():
            self._scan_directory(core_dir)

        # Scan adapters directory
        adapters_dir = self.root_dir / "adapters"
        if adapters_dir.exists():
            self._scan_directory(adapters_dir)

        # Scan tests directory for method calls
        tests_dir = self.root_dir / "tests"
        if tests_dir.exists():
            self._scan_directory(tests_dir, scan_definitions=False)

    def _scan_directory(self, directory: Path, scan_definitions: bool = True) -> None:
        """Recursively scan directory for Python files."""
        for py_file in directory.rglob("*.py"):
            # Skip __pycache__
            if "__pycache__" in str(py_file):
                continue

            # Skip archived code
            if "archive" in str(py_file):
                continue

            try:
                content = py_file.read_text()
                relative_path = py_file.relative_to(self.root_dir)

                if scan_definitions:
                    # Scan for event definitions
                    if "core/events" in str(py_file):
                        self._scan_event_definitions(content, str(relative_path))

                    # Scan for service method definitions
                    if "core/services" in str(py_file) and "_service.py" in py_file.name:
                        self._scan_service_methods(content, str(relative_path), py_file.stem)

                # Scan for event imports
                self._scan_event_imports(content, str(relative_path))

                # Scan for event publications
                self._scan_event_publications(content, str(relative_path))

                # Scan for event subscriptions
                self._scan_event_subscriptions(content, str(relative_path))

                # Scan for method calls
                self._scan_method_calls(content, str(relative_path))

            except Exception as e:
                if self.verbose:
                    print(f"  ⚠️  Error scanning {py_file}: {e}")

    def _scan_event_definitions(self, content: str, file_path: str) -> None:
        """Scan for event class definitions."""
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if class inherits from BaseEvent
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id == "BaseEvent":
                            self.event_definitions[node.name].append(file_path)
                            if self.verbose:
                                print(f"  📝 Found event definition: {node.name} in {file_path}")
        except SyntaxError:
            pass  # Skip files with syntax errors

    def _scan_event_imports(self, content: str, file_path: str) -> None:
        """Track event imports to correlate with usage."""
        # Pattern: from core.events import EventName
        # Pattern: from core.events.{module}_events import EventName
        import_pattern = r'from core\.events(?:\.\w+)? import .*?([A-Z]\w+(?:Event|Created|Updated|Deleted|Completed|Made|Recorded|Paid|Achieved|Mastered|Started|Changed|Assessed|Generated|Earned|Broken|Missed|Reached|Abandoned|Analyzed|Invalidated|Practiced|Milestone|Rescheduled|Applied|Task|Habit|Choice|Journal))'
        matches = re.finditer(import_pattern, content)
        for match in matches:
            event_class = match.group(1)
            self.event_imports[event_class].append(file_path)
            if self.verbose:
                print(f"  📥 Found event import: {event_class} in {file_path}")

    def _scan_event_publications(self, content: str, file_path: str) -> None:
        """Scan for event publications (event_bus.publish_async calls)."""
        # Pattern: event = SomeEvent(...)
        # followed by: await self.event_bus.publish_async(event)
        # OR: await event_bus.publish_async(SomeEvent(...))

        # Common event name suffixes
        event_suffixes = [
            "Event",
            "Created",
            "Updated",
            "Deleted",
            "Completed",
            "Started",
            "Changed",
            "Assessed",
            "Recorded",
            "Generated",
            "Earned",
            "Broken",
            "Missed",
            "Reached",
            "Made",
            "Abandoned",
            "Analyzed",
            "Invalidated",
            "Paid",
            "Mastered",
            "Practiced",
            "Milestone",
            "Rescheduled",
            "Achieved",  # GoalAchieved
            "Applied",  # KnowledgeBulkApplied
            "Task",  # KnowledgeAppliedInTask
            "Habit",  # KnowledgeBuiltIntoHabit
            "Choice",  # KnowledgeInformedChoice
            "Journal",  # KnowledgeReflectedInJournal
        ]

        # Build comprehensive pattern
        suffix_pattern = "|".join(event_suffixes)

        # Method 1: event = EventClass(...) then publish_async(event) OR publish_event(...)
        # Match any capitalized class ending with event suffixes
        event_instantiation_pattern = rf"(\w+)\s*=\s*([A-Z]\w*(?:{suffix_pattern}))\("
        matches = re.finditer(event_instantiation_pattern, content)
        for match in matches:
            event_class = match.group(2)
            # Check if followed by publish_async OR publish_event (increased lookahead for multiline constructors)
            if "publish_async" in content[match.end() : match.end() + 1500] or "publish_event" in content[match.end() : match.end() + 1500]:
                self.event_publications[event_class].append(file_path)
                if self.verbose:
                    print(f"  📤 Found event publication: {event_class} in {file_path}")

        # Method 2: publish_async(EventClass(...))
        direct_publish_pattern = rf"publish_async\(([A-Z]\w*(?:{suffix_pattern}))\("
        matches = re.finditer(direct_publish_pattern, content)
        for match in matches:
            event_class = match.group(1)
            self.event_publications[event_class].append(file_path)
            if self.verbose:
                print(f"  📤 Found event publication: {event_class} in {file_path}")

        # Method 3: publish_event(event_bus, EventClass(...), logger)
        # This is the MOST COMMON pattern in SKUEL
        helper_publish_pattern = rf"publish_event\([^,]+,\s*([A-Z]\w*(?:{suffix_pattern}))\("
        matches = re.finditer(helper_publish_pattern, content)
        for match in matches:
            event_class = match.group(1)
            self.event_publications[event_class].append(file_path)
            if self.verbose:
                print(f"  📤 Found event publication (helper): {event_class} in {file_path}")

    def _scan_event_subscriptions(self, content: str, file_path: str) -> None:
        """Scan for event subscriptions (event_bus.subscribe calls)."""
        # Pattern: event_bus.subscribe(EventClass, handler)
        subscription_pattern = r"\.subscribe\((\w+Event\w*),\s*\w+"
        matches = re.finditer(subscription_pattern, content)
        for match in matches:
            event_class = match.group(1)
            self.event_subscriptions[event_class].append(file_path)
            if self.verbose:
                print(f"  📥 Found event subscription: {event_class} in {file_path}")

    def _scan_service_methods(self, content: str, file_path: str, service_name: str) -> None:
        """Scan for public method definitions in service files."""
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.AsyncFunctionDef | ast.FunctionDef):
                            # Public methods (not starting with _)
                            if not item.name.startswith("_") and item.name not in [
                                "__init__",
                                "__str__",
                                "__repr__",
                            ]:
                                self.service_methods[service_name][item.name].append(file_path)
                                if self.verbose:
                                    print(
                                        f"  🔧 Found service method: {service_name}.{item.name} in {file_path}"
                                    )
        except SyntaxError:
            pass

    def _scan_method_calls(self, content: str, file_path: str) -> None:
        """Scan for method calls including reflection patterns."""
        # Pattern: .method_name(  or  service.method_name(
        method_call_pattern = r"\.(\w+)\("
        matches = re.finditer(method_call_pattern, content)
        for match in matches:
            method_name = match.group(1)
            self.method_calls[method_name].append(file_path)

            # Track service method calls
            # Pattern: service_name.method_name(
            service_call_pattern = r"(\w+_service)\.(\w+)\("
            service_matches = re.finditer(service_call_pattern, content)
            for smatch in service_matches:
                service_name = smatch.group(1)
                method_name = smatch.group(2)
                self.service_method_calls[service_name][method_name].append(file_path)

        # NEW: Detect reflection-based method calls
        # Pattern: getattr(obj, "method_name") or getattr(Service, "method_name")
        reflection_pattern = r'getattr\([^,]+,\s*["\'](\w+)["\']'
        matches = re.finditer(reflection_pattern, content)
        for match in matches:
            method_name = match.group(1)
            self.method_calls[method_name].append(file_path)
            self.reflection_calls[method_name].append(file_path)
            if self.verbose:
                print(f"  🔍 Found reflection call: {method_name} in {file_path}")

        # NEW: Track dynamic method construction (f"{var}_method_suffix")
        # Pattern: getattr(obj, f"{entity}_create_to_pure") or similar
        # This catches ConversionService patterns like {entity}_to_pure, {entity}_to_dto
        dynamic_pattern = r'getattr\([^,]+,\s*f["\'][^"\']*\{[^}]+\}[^"\']*?(_to_\w+|_create_to_\w+|_update_to_\w+)["\']'
        matches = re.finditer(dynamic_pattern, content)
        for match in matches:
            method_suffix = match.group(1)
            # Mark this as a reflection pattern usage
            self.reflection_calls[f"*{method_suffix}"].append(file_path)
            if self.verbose:
                print(f"  🔍 Found dynamic reflection pattern: *{method_suffix} in {file_path}")

        # NEW: Special pattern for ConversionService - any getattr on ConversionService/V2 is reflection
        # Pattern: getattr(ConversionService[V2], ...)
        conversion_service_pattern = r'getattr\((ConversionService(?:V2)?),\s*(\w+)'
        matches = re.finditer(conversion_service_pattern, content)
        for match in matches:
            # Mark all conversion service methods as reflection-used
            self.reflection_calls["*conversion_service*"].append(file_path)
            if self.verbose:
                print(f"  🔍 Found ConversionService reflection usage in {file_path}")

    def find_unused_events(self) -> list[dict[str, Any]]:
        """Find events that are defined but never published."""
        unused = []

        for event_class, def_files in self.event_definitions.items():
            pub_files = self.event_publications.get(event_class, [])

            if not pub_files:
                unused.append(
                    {
                        "event_class": event_class,
                        "defined_in": def_files,
                        "published_in": [],
                        "subscribed_in": self.event_subscriptions.get(event_class, []),
                    }
                )

        return unused

    def find_dead_subscriptions(self) -> list[dict[str, Any]]:
        """Find event subscriptions where the event is never published."""
        dead_subs = []

        for event_class, sub_files in self.event_subscriptions.items():
            pub_files = self.event_publications.get(event_class, [])

            if not pub_files:
                dead_subs.append(
                    {
                        "event_class": event_class,
                        "subscribed_in": sub_files,
                        "published_in": [],
                        "defined_in": self.event_definitions.get(event_class, []),
                    }
                )

        return dead_subs

    def find_unused_service_methods(self) -> list[dict[str, Any]]:
        """Find public service methods that are never called externally."""
        unused = []

        for service_name, methods in self.service_methods.items():
            for method_name, def_files in methods.items():
                # Check if method is called anywhere
                call_files = self.method_calls.get(method_name, [])

                # Filter out self-calls (calls within the same file)
                external_calls = [f for f in call_files if f not in def_files]

                if not external_calls:
                    unused.append(
                        {
                            "service": service_name,
                            "method": method_name,
                            "defined_in": def_files,
                            "called_in": call_files,
                            "external_calls": external_calls,
                        }
                    )

        return unused

    def _is_reflection_method(self, service: str, method: str) -> bool:
        """Check if method is used via reflection."""
        # Direct reflection call
        if method in self.reflection_calls:
            return True

        # ConversionService - if we found any ConversionService reflection usage
        if service == "conversion_service":
            # If we detected ConversionService reflection usage, all its methods are reflection-used
            if "*conversion_service*" in self.reflection_calls:
                return True
            # Check for patterns like *_to_pure, *_to_dto, etc.
            for pattern in self.reflection_calls.keys():
                if pattern.startswith("*") and pattern[1:] in method:
                    return True

        return False

    def generate_report(
        self, check_events: bool = True, check_methods: bool = True
    ) -> dict[str, Any]:
        """Generate comprehensive bloat report."""
        report = {}

        if check_events:
            unused_events = self.find_unused_events()
            dead_subscriptions = self.find_dead_subscriptions()

            report["unused_events"] = unused_events
            report["dead_subscriptions"] = dead_subscriptions
            report["total_events"] = len(self.event_definitions)
            report["unused_event_count"] = len(unused_events)
            report["dead_subscription_count"] = len(dead_subscriptions)

        if check_methods:
            unused_service_methods = self.find_unused_service_methods()

            report["unused_service_methods"] = unused_service_methods
            report["total_service_methods"] = sum(
                len(methods) for methods in self.service_methods.values()
            )
            report["unused_service_method_count"] = len(unused_service_methods)

        return report

    def print_report(self, report: dict[str, Any]) -> None:
        """Print formatted bloat report."""
        print(f"\n{BOLD}{'=' * 80}{RESET}")
        print(f"{BOLD}{CYAN}📊 BLOAT DETECTION REPORT{RESET}")
        print(f"{BOLD}{'=' * 80}{RESET}\n")

        # Unused Events Section
        if "unused_events" in report:
            unused_events = report["unused_events"]
            total_events = report["total_events"]
            unused_count = report["unused_event_count"]

            print(f"{BOLD}🔔 Events Analysis{RESET}")
            print(f"  Total events defined: {total_events}")
            print(f"  Unused events: {YELLOW}{unused_count}{RESET}")

            if unused_events:
                print(f"\n{YELLOW}⚠️  Unused Events (defined but never published):{RESET}\n")
                for item in unused_events:
                    print(f"  {RED}✗{RESET} {BOLD}{item['event_class']}{RESET}")
                    print(f"    Defined in: {', '.join(item['defined_in'])}")
                    if item["subscribed_in"]:
                        print(
                            f"    {YELLOW}⚠️  Has subscribers!{RESET} {', '.join(item['subscribed_in'])}"
                        )
                    print()
            else:
                print(f"  {GREEN}✓ No unused events found!{RESET}\n")

        # Dead Subscriptions Section
        if "dead_subscriptions" in report:
            dead_subs = report["dead_subscriptions"]
            dead_count = report["dead_subscription_count"]

            if dead_count > 0:
                print(f"{BOLD}📥 Event Subscriptions Analysis{RESET}")
                print(f"  Dead subscriptions: {YELLOW}{dead_count}{RESET}\n")

                print(f"{YELLOW}⚠️  Dead Subscriptions (subscribed but never published):{RESET}\n")
                for item in dead_subs:
                    print(f"  {RED}✗{RESET} {BOLD}{item['event_class']}{RESET}")
                    print(f"    Subscribed in: {', '.join(item['subscribed_in'])}")
                    if item["defined_in"]:
                        print(f"    Defined in: {', '.join(item['defined_in'])}")
                    else:
                        print(f"    {RED}⚠️  Event not defined!{RESET}")
                    print()

        # Unused Service Methods Section
        if "unused_service_methods" in report:
            unused_methods = report["unused_service_methods"]
            total_methods = report["total_service_methods"]
            unused_method_count = report["unused_service_method_count"]

            print(f"\n{BOLD}🔧 Service Methods Analysis{RESET}")
            print(f"  Total public service methods: {total_methods}")
            print(f"  Potentially unused methods: {YELLOW}{unused_method_count}{RESET}")

            if unused_methods:
                print(
                    f"\n{YELLOW}⚠️  Potentially Unused Service Methods (no external calls):{RESET}\n"
                )

                # Group by service
                by_service: dict[str, list] = defaultdict(list)
                for item in unused_methods:
                    by_service[item["service"]].append(item)

                for service_name in sorted(by_service.keys()):
                    methods = by_service[service_name]
                    print(f"  {BOLD}{service_name}{RESET} ({len(methods)} methods):")
                    for item in methods:
                        print(f"    {RED}✗{RESET} {item['method']}")
                        if item["called_in"]:
                            print(f"      (called internally in {len(item['called_in'])} places)")
                        # NEW: Note if used via reflection
                        if self._is_reflection_method(item['service'], item['method']):
                            print(f"      {CYAN}ℹ️  Used via reflection (getattr){RESET}")
                    print()
            else:
                print(f"  {GREEN}✓ No unused service methods found!{RESET}\n")

        # Summary
        print(f"{BOLD}{'=' * 80}{RESET}")
        print(f"{BOLD}📈 Summary{RESET}\n")

        total_issues = 0
        if "unused_event_count" in report:
            total_issues += report["unused_event_count"]
            total_issues += report.get("dead_subscription_count", 0)

        if "unused_service_method_count" in report:
            total_issues += report["unused_service_method_count"]

        if total_issues == 0:
            print(f"{GREEN}{BOLD}✅ No bloat detected! Codebase is clean.{RESET}\n")
        else:
            print(f"{YELLOW}Found {total_issues} potential bloat issues.{RESET}")
            print(
                f"{CYAN}Review these items to determine if they should be removed or implemented.{RESET}\n"
            )

        print(f"{BOLD}{'=' * 80}{RESET}\n")


def main():
    """Run bloat detection."""
    parser = argparse.ArgumentParser(description="Detect unused code in SKUEL codebase")
    parser.add_argument("--events-only", action="store_true", help="Check events only")
    parser.add_argument("--methods-only", action="store_true", help="Check methods only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Determine what to check
    check_events = not args.methods_only
    check_methods = not args.events_only

    # Initialize detector
    root_dir = Path(__file__).parent.parent
    detector = BloatDetector(root_dir, verbose=args.verbose)

    # Scan codebase
    detector.scan_codebase()

    # Generate report
    report = detector.generate_report(check_events=check_events, check_methods=check_methods)

    # Print report
    detector.print_report(report)


if __name__ == "__main__":
    main()
