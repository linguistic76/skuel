---
title: SKUEL Enum Reference
updated: 2026-01-29
status: current
category: reference
tags: [enum, reference, roles]
related: [ADR-018-user-roles-four-tier-system.md]
---

# SKUEL Enum Reference

**Generated from:** `core/models/enums/` (all enum modules)
**Total Enums:** 35

This document provides a complete reference for all enums used in SKUEL.
Enums are the single source of truth for valid values across all domains.

## Table of Contents

- [KuStatus](#activitystatus)
- [ActivityType](#activitytype)
- [BridgeType](#bridgetype)
- [CacheStrategy](#cachestrategy)
- [CompletionStatus](#completionstatus)
- [ContentType](#contenttype)
- [Context](#context)
- [ConversationState](#conversationstate)
- [Domain](#domain)
- [EnergyLevel](#energylevel)
- [ErrorSeverity](#errorseverity)
- [ExtractionMethod](#extractionmethod)
- [FacetType](#facettype)
- [GoalStatus](#goalstatus)
- [GuidanceMode](#guidancemode)
- [HealthStatus](#healthstatus)
- [Intent](#intent)
- [KnowledgeStatus](#knowledgestatus)
- [KnowledgeType](#knowledgetype)
- [LearningLevel](#learninglevel)
- [LearningModality](#learningmodality)
- [MasteryStatus](#masterystatus)
- [MessageRole](#messagerole)
- [Personality](#personality)
- [PracticeLevel](#practicelevel)
- [Priority](#priority)
- [RecurrencePattern](#recurrencepattern)
- [RelationshipType](#relationshiptype)
- [ResponseTone](#responsetone)
- [SearchScope](#searchscope)
- [SeverityLevel](#severitylevel)
- [TimeOfDay](#timeofday)
- [TrendDirection](#trenddirection)
- [UserRole](#userrole)
- [Visibility](#visibility)

---

### KuStatus

Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.

**Valid values:**

- `draft` (DRAFT): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.
- `scheduled` (SCHEDULED): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.
- `in_progress` (IN_PROGRESS): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.
- `paused` (PAUSED): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.
- `blocked` (BLOCKED): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.
- `completed` (COMPLETED): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.
- `cancelled` (CANCELLED): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.
- `postponed` (POSTPONED): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.
- `failed` (FAILED): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.
- `recurring` (RECURRING): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.
- `archived` (ARCHIVED): Universal status for any trackable activity.

Not all statuses apply to all entity types, but having a unified
set allows for consistent state management across the system.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import KuStatus

# Using enum value
status = KuStatus.DRAFT
print(status.value)  # "draft"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### ActivityType

Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.

**Valid values:**

- `task` (TASK): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `habit` (HABIT): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `event` (EVENT): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `learning` (LEARNING): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `milestone` (MILESTONE): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `deadline` (DEADLINE): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `meeting` (MEETING): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `practice` (PRACTICE): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `review` (REVIEW): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `break` (BREAK): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `block` (BLOCK): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.
- `placeholder` (PLACEHOLDER): Types of activities that can appear on a calendar or be tracked.

This enum defines the fundamental types of trackable entities
in the system. Each type may have different behaviors and
rendering styles on the calendar.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import ActivityType

# Using enum value
status = ActivityType.TASK
print(status.value)  # "task"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### BridgeType

Types of knowledge bridges for cross-domain learning

**Valid values:**

- `direct` (DIRECT): Types of knowledge bridges for cross-domain learning
- `analogical` (ANALOGICAL): Types of knowledge bridges for cross-domain learning
- `methodological` (METHODOLOGICAL): Types of knowledge bridges for cross-domain learning
- `skill_transfer` (SKILL_TRANSFER): Types of knowledge bridges for cross-domain learning

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import BridgeType

# Using enum value
status = BridgeType.DIRECT
print(status.value)  # "direct"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### CacheStrategy

Caching strategies

**Valid values:**

- `no_cache` (NO_CACHE): Caching strategies
- `short` (SHORT): Caching strategies
- `medium` (MEDIUM): Caching strategies
- `long` (LONG): Caching strategies
- `persistent` (PERSISTENT): Caching strategies

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import CacheStrategy

# Using enum value
status = CacheStrategy.NO_CACHE
print(status.value)  # "no_cache"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### CompletionStatus

Status for tracking completion of activities, especially habits.

More nuanced than just complete/incomplete to track quality.

**Valid values:**

- `done` (DONE): Status for tracking completion of activities, especially habits.

More nuanced than just complete/incomplete to track quality.
- `partial` (PARTIAL): Status for tracking completion of activities, especially habits.

More nuanced than just complete/incomplete to track quality.
- `skipped` (SKIPPED): Status for tracking completion of activities, especially habits.

More nuanced than just complete/incomplete to track quality.
- `missed` (MISSED): Status for tracking completion of activities, especially habits.

More nuanced than just complete/incomplete to track quality.
- `paused` (PAUSED): Status for tracking completion of activities, especially habits.

More nuanced than just complete/incomplete to track quality.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import CompletionStatus

# Using enum value
status = CompletionStatus.DONE
print(status.value)  # "done"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### ContentType

Types of knowledge content

**Valid values:**

- `concept` (CONCEPT): Types of knowledge content
- `practice` (PRACTICE): Types of knowledge content
- `principle` (PRINCIPLE): Types of knowledge content
- `theory` (THEORY): Types of knowledge content
- `example` (EXAMPLE): Types of knowledge content
- `explanation` (EXPLANATION): Types of knowledge content
- `reference` (REFERENCE): Types of knowledge content

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import ContentType

# Using enum value
status = ContentType.CONCEPT
print(status.value)  # "concept"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### Context

Context where activity can be performed

**Valid values:**

- `home` (HOME): Context where activity can be performed
- `work` (WORK): Context where activity can be performed
- `computer` (COMPUTER): Context where activity can be performed
- `phone` (PHONE): Context where activity can be performed
- `errands` (ERRANDS): Context where activity can be performed
- `anywhere` (ANYWHERE): Context where activity can be performed

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import Context

# Using enum value
status = Context.HOME
print(status.value)  # "home"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### ConversationState

State of a conversation session

**Valid values:**

- `idle` (IDLE): State of a conversation session
- `awaiting_clarification` (AWAITING_CLARIFICATION): State of a conversation session
- `extracting_facets` (EXTRACTING_FACETS): State of a conversation session
- `searching` (SEARCHING): State of a conversation session
- `generating_response` (GENERATING_RESPONSE): State of a conversation session
- `responding` (RESPONDING): State of a conversation session
- `error` (ERROR): State of a conversation session

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import ConversationState

# Using enum value
status = ConversationState.IDLE
print(status.value)  # "idle"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### Domain

Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.

**Valid values:**

- `knowledge` (KNOWLEDGE): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `learning` (LEARNING): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `tasks` (TASKS): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `habits` (HABITS): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `finance` (FINANCE): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `events` (EVENTS): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `journals` (JOURNALS): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `principles` (PRINCIPLES): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `goals` (GOALS): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `choices` (CHOICES): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `system` (SYSTEM): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `all` (ALL): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `tech` (TECH): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `business` (BUSINESS): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `personal` (PERSONAL): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `health` (HEALTH): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `education` (EDUCATION): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `creative` (CREATIVE): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `research` (RESEARCH): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `social` (SOCIAL): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `meta` (META): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.
- `cross_domain` (CROSS_DOMAIN): Core domains in the SKUEL system.
Each domain represents a distinct area of functionality.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import Domain

# Using enum value
status = Domain.KNOWLEDGE
print(status.value)  # "knowledge"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### EnergyLevel

Energy level required or available for activities.

Used for matching tasks to energy states and optimal scheduling.

**Valid values:**

- `low` (LOW): Energy level required or available for activities.

Used for matching tasks to energy states and optimal scheduling.
- `medium` (MEDIUM): Energy level required or available for activities.

Used for matching tasks to energy states and optimal scheduling.
- `high` (HIGH): Energy level required or available for activities.

Used for matching tasks to energy states and optimal scheduling.
- `variable` (VARIABLE): Energy level required or available for activities.

Used for matching tasks to energy states and optimal scheduling.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import EnergyLevel

# Using enum value
status = EnergyLevel.LOW
print(status.value)  # "low"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### ErrorSeverity

Severity of errors

**Valid values:**

- `low` (LOW): Severity of errors
- `medium` (MEDIUM): Severity of errors
- `high` (HIGH): Severity of errors
- `critical` (CRITICAL): Severity of errors

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import ErrorSeverity

# Using enum value
status = ErrorSeverity.LOW
print(status.value)  # "low"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### ExtractionMethod

Method used for facet/intent extraction

**Valid values:**

- `pattern` (PATTERN): Method used for facet/intent extraction
- `embedding` (EMBEDDING): Method used for facet/intent extraction
- `llm` (LLM): Method used for facet/intent extraction
- `hybrid` (HYBRID): Method used for facet/intent extraction

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import ExtractionMethod

# Using enum value
status = ExtractionMethod.PATTERN
print(status.value)  # "pattern"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### FacetType

Types of facets for filtering and categorization

**Valid values:**

- `domain` (DOMAIN): Types of facets for filtering and categorization
- `tag` (TAG): Types of facets for filtering and categorization
- `category` (CATEGORY): Types of facets for filtering and categorization
- `status` (STATUS): Types of facets for filtering and categorization
- `priority` (PRIORITY): Types of facets for filtering and categorization
- `date_range` (DATE_RANGE): Types of facets for filtering and categorization
- `author` (AUTHOR): Types of facets for filtering and categorization
- `type` (TYPE): Types of facets for filtering and categorization
- `difficulty` (DIFFICULTY): Types of facets for filtering and categorization
- `mastery` (MASTERY): Types of facets for filtering and categorization

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import FacetType

# Using enum value
status = FacetType.DOMAIN
print(status.value)  # "domain"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### GoalStatus

Current state of a goal

**Valid values:**

- `planned` (PLANNED): Current state of a goal
- `active` (ACTIVE): Current state of a goal
- `paused` (PAUSED): Current state of a goal
- `achieved` (ACHIEVED): Current state of a goal
- `cancelled` (CANCELLED): Current state of a goal
- `failed` (FAILED): Current state of a goal

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import GoalStatus

# Using enum value
status = GoalStatus.PLANNED
print(status.value)  # "planned"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### GuidanceMode

Level of guidance in learning/tasks

**Valid values:**

- `minimal` (MINIMAL): Level of guidance in learning/tasks
- `balanced` (BALANCED): Level of guidance in learning/tasks
- `detailed` (DETAILED): Level of guidance in learning/tasks
- `adaptive` (ADAPTIVE): Level of guidance in learning/tasks

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import GuidanceMode

# Using enum value
status = GuidanceMode.MINIMAL
print(status.value)  # "minimal"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### HealthStatus

System health status levels

**Valid values:**

- `healthy` (HEALTHY): System health status levels
- `warning` (WARNING): System health status levels
- `critical` (CRITICAL): System health status levels
- `unknown` (UNKNOWN): System health status levels

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import HealthStatus

# Using enum value
status = HealthStatus.HEALTHY
print(status.value)  # "healthy"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### Intent

User intent detected from queries and conversations.
Unified from search intents and conversation intents.

**Valid values:**

- `general` (GENERAL): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `learning` (LEARNING): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `search` (SEARCH): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `create` (CREATE): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `update` (UPDATE): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `delete` (DELETE): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `explore` (EXPLORE): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `discover` (DISCOVER): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `practice` (PRACTICE): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `task_management` (TASK_MANAGEMENT): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `habit_tracking` (HABIT_TRACKING): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `financial` (FINANCIAL): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `help` (HELP): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `clarify` (CLARIFY): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `review` (REVIEW): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `reflect` (REFLECT): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `explain` (EXPLAIN): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `summarize` (SUMMARIZE): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `analyze` (ANALYZE): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `schedule` (SCHEDULE): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `track` (TRACK): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `connect` (CONNECT): User intent detected from queries and conversations.
Unified from search intents and conversation intents.
- `organize` (ORGANIZE): User intent detected from queries and conversations.
Unified from search intents and conversation intents.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import Intent

# Using enum value
status = Intent.GENERAL
print(status.value)  # "general"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### KnowledgeCategory

Categories for organizing knowledge

**Valid values:**

- `technical` (TECHNICAL): Categories for organizing knowledge
- `business` (BUSINESS): Categories for organizing knowledge
- `creative` (CREATIVE): Categories for organizing knowledge
- `personal` (PERSONAL): Categories for organizing knowledge
- `health` (HEALTH): Categories for organizing knowledge
- `finance` (FINANCE): Categories for organizing knowledge
- `educational` (EDUCATIONAL): Categories for organizing knowledge
- `other` (OTHER): Categories for organizing knowledge

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

---

### KnowledgeStatus

Domain-specific status for knowledge units.
Maps to KuStatus where applicable for consistency.

**Valid values:**

- `draft` (DRAFT): Domain-specific status for knowledge units.
Maps to KuStatus where applicable for consistency.
- `published` (PUBLISHED): Domain-specific status for knowledge units.
Maps to KuStatus where applicable for consistency.
- `archived` (ARCHIVED): Domain-specific status for knowledge units.
Maps to KuStatus where applicable for consistency.
- `under_review` (UNDER_REVIEW): Domain-specific status for knowledge units.
Maps to KuStatus where applicable for consistency.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import KnowledgeStatus

# Using enum value
status = KnowledgeStatus.DRAFT
print(status.value)  # "draft"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### KnowledgeType

Types of knowledge for classification

**Valid values:**

- `declarative` (DECLARATIVE): Types of knowledge for classification
- `procedural` (PROCEDURAL): Types of knowledge for classification
- `conceptual` (CONCEPTUAL): Types of knowledge for classification
- `metacognitive` (METACOGNITIVE): Types of knowledge for classification

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import KnowledgeType

# Using enum value
status = KnowledgeType.DECLARATIVE
print(status.value)  # "declarative"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### LearningLevel

Learning proficiency levels for users and content.

Used to match users with appropriate content difficulty.

**Valid values:**

- `beginner` (BEGINNER): Learning proficiency levels for users and content.

Used to match users with appropriate content difficulty.
- `intermediate` (INTERMEDIATE): Learning proficiency levels for users and content.

Used to match users with appropriate content difficulty.
- `advanced` (ADVANCED): Learning proficiency levels for users and content.

Used to match users with appropriate content difficulty.
- `expert` (EXPERT): Learning proficiency levels for users and content.

Used to match users with appropriate content difficulty.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import LearningLevel

# Using enum value
status = LearningLevel.BEGINNER
print(status.value)  # "beginner"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### LearningModality

Preferred learning modalities

**Valid values:**

- `visual` (VISUAL): Preferred learning modalities
- `auditory` (AUDITORY): Preferred learning modalities
- `reading` (READING): Preferred learning modalities
- `kinesthetic` (KINESTHETIC): Preferred learning modalities
- `interactive` (INTERACTIVE): Preferred learning modalities
- `video` (VIDEO): Preferred learning modalities
- `practice` (PRACTICE): Preferred learning modalities

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import LearningModality

# Using enum value
status = LearningModality.VISUAL
print(status.value)  # "visual"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### MasteryStatus

Mastery status for knowledge/skills

**Valid values:**

- `not_started` (NOT_STARTED): Mastery status for knowledge/skills
- `introduced` (INTRODUCED): Mastery status for knowledge/skills
- `practicing` (PRACTICING): Mastery status for knowledge/skills
- `competent` (COMPETENT): Mastery status for knowledge/skills
- `proficient` (PROFICIENT): Mastery status for knowledge/skills
- `mastered` (MASTERED): Mastery status for knowledge/skills
- `reviewing` (REVIEWING): Mastery status for knowledge/skills

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import MasteryStatus

# Using enum value
status = MasteryStatus.NOT_STARTED
print(status.value)  # "not_started"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### MessageRole

Role of message sender

**Valid values:**

- `user` (USER): Role of message sender
- `assistant` (ASSISTANT): Role of message sender
- `system` (SYSTEM): Role of message sender

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import MessageRole

# Using enum value
status = MessageRole.USER
print(status.value)  # "user"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### Personality

AI personality modes and user personality types.
Shapes the overall character of responses and interactions.

**Valid values:**

- `knowledgeable_friend` (KNOWLEDGEABLE_FRIEND): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `tutor` (TUTOR): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `coach` (COACH): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `professional` (PROFESSIONAL): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `casual` (CASUAL): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `socratic` (SOCRATIC): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `achiever` (ACHIEVER): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `explorer` (EXPLORER): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `socializer` (SOCIALIZER): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `analytical` (ANALYTICAL): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `creative` (CREATIVE): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.
- `methodical` (METHODICAL): AI personality modes and user personality types.
Shapes the overall character of responses and interactions.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import Personality

# Using enum value
status = Personality.KNOWLEDGEABLE_FRIEND
print(status.value)  # "knowledgeable_friend"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### PracticeLevel

Difficulty/expertise levels

**Valid values:**

- `beginner` (BEGINNER): Difficulty/expertise levels
- `intermediate` (INTERMEDIATE): Difficulty/expertise levels
- `advanced` (ADVANCED): Difficulty/expertise levels
- `expert` (EXPERT): Difficulty/expertise levels

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import PracticeLevel

# Using enum value
status = PracticeLevel.BEGINNER
print(status.value)  # "beginner"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### Priority

Universal priority levels used across all entities.

Used by: Tasks, Events, Habits, Learning Sessions

**Valid values:**

- `low` (LOW): Universal priority levels used across all entities.

Used by: Tasks, Events, Habits, Learning Sessions
- `medium` (MEDIUM): Universal priority levels used across all entities.

Used by: Tasks, Events, Habits, Learning Sessions
- `high` (HIGH): Universal priority levels used across all entities.

Used by: Tasks, Events, Habits, Learning Sessions
- `critical` (CRITICAL): Universal priority levels used across all entities.

Used by: Tasks, Events, Habits, Learning Sessions

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import Priority

# Using enum value
status = Priority.LOW
print(status.value)  # "low"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### RecurrencePattern

Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.

**Valid values:**

- `none` (NONE): Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.
- `daily` (DAILY): Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.
- `weekdays` (WEEKDAYS): Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.
- `weekends` (WEEKENDS): Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.
- `weekly` (WEEKLY): Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.
- `biweekly` (BIWEEKLY): Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.
- `monthly` (MONTHLY): Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.
- `quarterly` (QUARTERLY): Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.
- `yearly` (YEARLY): Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.
- `custom` (CUSTOM): Universal recurrence patterns for any repeating activity.

Used by habits, recurring tasks, events, and learning sessions.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import RecurrencePattern

# Using enum value
status = RecurrencePattern.NONE
print(status.value)  # "none"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### RelationshipType

Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.

**Valid values:**

- `blocks` (BLOCKS): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `requires` (REQUIRES): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `enables` (ENABLES): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `parent_of` (PARENT_OF): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `child_of` (CHILD_OF): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `subtask_of` (SUBTASK_OF): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `parent_child` (PARENT_CHILD): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `related_to` (RELATED_TO): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `related` (RELATED): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `part_of` (PART_OF): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `supports` (SUPPORTS): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `suggests` (SUGGESTS): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `conflicts_with` (CONFLICTS_WITH): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `conflicts` (CONFLICTS): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `duplicates` (DUPLICATES): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `continues` (CONTINUES): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `before` (BEFORE): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `after` (AFTER): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `during` (DURING): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `overlaps` (OVERLAPS): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `prerequisite_for` (PREREQUISITE_FOR): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `prerequisite` (PREREQUISITE): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `builds_on` (BUILDS_ON): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `practices` (PRACTICES): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `triggers` (TRIGGERS): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `reinforces` (REINFORCES): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `replaces` (REPLACES): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `mastered` (MASTERED): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `in_progress` (IN_PROGRESS): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `needs_review` (NEEDS_REVIEW): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `struggling_with` (STRUGGLING_WITH): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `assigned_to` (ASSIGNED_TO): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `owns` (OWNS): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `completed_task` (COMPLETED_TASK): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `delegated` (DELEGATED): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `requires_knowledge` (REQUIRES_KNOWLEDGE): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `contributes_to_goal` (CONTRIBUTES_TO_GOAL): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `depends_on` (DEPENDS_ON): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `blocked_by` (BLOCKED_BY): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `attending` (ATTENDING): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `organizing` (ORGANIZING): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `invited_to` (INVITED_TO): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `presents_at` (PRESENTS_AT): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `covers_knowledge` (COVERS_KNOWLEDGE): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `advances_goal` (ADVANCES_GOAL): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `has_goal` (HAS_GOAL): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `supported_by` (SUPPORTED_BY): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `guided_by` (GUIDED_BY): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `has_habit` (HAS_HABIT): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `develops_skill` (DEVELOPS_SKILL): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `embodies` (EMBODIES): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `holds_principle` (HOLDS_PRINCIPLE): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `based_on_knowledge` (BASED_ON_KNOWLEDGE): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `supports_goal` (SUPPORTS_GOAL): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `reinforces_habit` (REINFORCES_HABIT): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `aligns_with_principle` (ALIGNS_WITH_PRINCIPLE): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `informed_by_knowledge` (INFORMED_BY_KNOWLEDGE): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `interested_in` (INTERESTED_IN): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `bookmarked` (BOOKMARKED): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `completed` (COMPLETED): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.
- `enrolled` (ENROLLED): Universal relationship types that can exist between any entities.

Covers task dependencies, learning prerequisites, habit chains, and all
cross-entity relationships in the system.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import RelationshipType

# Using enum value
status = RelationshipType.BLOCKS
print(status.value)  # "blocks"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### ResponseTone

Tone for system responses

**Valid values:**

- `neutral` (NEUTRAL): Tone for system responses
- `friendly` (FRIENDLY): Tone for system responses
- `professional` (PROFESSIONAL): Tone for system responses
- `encouraging` (ENCOURAGING): Tone for system responses
- `motivational` (MOTIVATIONAL): Tone for system responses
- `analytical` (ANALYTICAL): Tone for system responses
- `concise` (CONCISE): Tone for system responses
- `detailed` (DETAILED): Tone for system responses

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import ResponseTone

# Using enum value
status = ResponseTone.NEUTRAL
print(status.value)  # "neutral"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### SearchScope

Scope of search operations

**Valid values:**

- `local` (LOCAL): Scope of search operations
- `cross_domain` (CROSS_DOMAIN): Scope of search operations
- `related` (RELATED): Scope of search operations
- `deep` (DEEP): Scope of search operations

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import SearchScope

# Using enum value
status = SearchScope.LOCAL
print(status.value)  # "local"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### SeverityLevel

Severity levels for issues, gaps, and alerts

**Valid values:**

- `high` (HIGH): Severity levels for issues, gaps, and alerts
- `medium` (MEDIUM): Severity levels for issues, gaps, and alerts
- `low` (LOW): Severity levels for issues, gaps, and alerts

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import SeverityLevel

# Using enum value
status = SeverityLevel.HIGH
print(status.value)  # "high"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### TimeOfDay

Preferred time of day for activities.

Used for scheduling preferences and habit timing.

**Valid values:**

- `early_morning` (EARLY_MORNING): Preferred time of day for activities.

Used for scheduling preferences and habit timing.
- `morning` (MORNING): Preferred time of day for activities.

Used for scheduling preferences and habit timing.
- `afternoon` (AFTERNOON): Preferred time of day for activities.

Used for scheduling preferences and habit timing.
- `evening` (EVENING): Preferred time of day for activities.

Used for scheduling preferences and habit timing.
- `night` (NIGHT): Preferred time of day for activities.

Used for scheduling preferences and habit timing.
- `late_night` (LATE_NIGHT): Preferred time of day for activities.

Used for scheduling preferences and habit timing.
- `anytime` (ANYTIME): Preferred time of day for activities.

Used for scheduling preferences and habit timing.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import TimeOfDay

# Using enum value
status = TimeOfDay.EARLY_MORNING
print(status.value)  # "early_morning"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### TrendDirection

Direction of trends in analytics and dashboards

**Valid values:**

- `increasing` (INCREASING): Direction of trends in analytics and dashboards
- `decreasing` (DECREASING): Direction of trends in analytics and dashboards
- `stable` (STABLE): Direction of trends in analytics and dashboards

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import TrendDirection

# Using enum value
status = TrendDirection.INCREASING
print(status.value)  # "increasing"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

### UserRole

**Location:** `core/models/enums/user_enums.py`

**Added:** December 2025 (ADR-018)

Four-tier user authorization hierarchy. Higher levels inherit permissions from lower levels.

**Valid values:**

| Value | Level | Description |
|-------|-------|-------------|
| `registered` (REGISTERED) | 0 | Free trial with limited access (5 KUs, 1 LP, 10 tasks, 5 goals, 5 habits, 10 events, 5 principles, 5 choices, 3 journals) |
| `member` (MEMBER) | 1 | Paid subscription (unlimited access) |
| `teacher` (TEACHER) | 2 | Content creator (Member + create/edit KU, LP, MOC) |
| `admin` (ADMIN) | 3 | System manager (Teacher + user management) |

**Key Methods:**

- `has_permission(required: UserRole) -> bool`: Check if this role has permission for required level
- `is_subscriber() -> bool`: True if MEMBER or above (paid users)
- `is_trial() -> bool`: True if REGISTERED (free trial users)
- `can_create_curriculum() -> bool`: True if TEACHER or above
- `can_manage_users() -> bool`: True only for ADMIN
- `from_string(value: str) -> UserRole | None`: Parse string to UserRole
- `default() -> UserRole`: Returns REGISTERED (default for new users)

**Usage Example:**

```python
from core.models.enums import UserRole

# Check hierarchy
user_role = UserRole.TEACHER
if user_role.has_permission(UserRole.MEMBER):
    print("User is a paid subscriber")  # True - TEACHER >= MEMBER

# Convenience methods
if user_role.can_create_curriculum():
    print("Can create KU/LP/MOC")  # True - TEACHER+

# Parse from string
role = UserRole.from_string("admin")  # Returns UserRole.ADMIN
```

**See:** `/docs/decisions/ADR-018-user-roles-four-tier-system.md`

---

### ContextHealthScore

**Location:** `core/models/enums/user_enums.py`

**Added:** January 2026 (User Context Intelligence)

Health score assessment for UserContext quality across multiple dimensions. Provides semantic scoring (0.0-1.0), visual feedback (colors/icons), and tier-based evaluation.

**Valid values:**

| Value | Numeric Score | Color | Icon | Description |
|-------|---------------|-------|------|-------------|
| `poor` (POOR) | 0.25 | Red (#ef4444) | 🔴 | Critical issues, immediate attention needed |
| `fair` (FAIR) | 0.50 | Yellow (#eab308) | 🟡 | Some gaps, improvement recommended |
| `good` (GOOD) | 0.75 | Green (#22c55e) | 🟢 | Healthy state, minor optimizations possible |
| `excellent` (EXCELLENT) | 1.00 | Blue (#3b82f6) | 🟢 | Optimal state across all dimensions |

**Key Methods:**

- `get_numeric() -> float`: Returns 0.0-1.0 score (0.25, 0.50, 0.75, 1.00)
- `get_color() -> str`: Returns hex color code for UI display
- `get_icon() -> str`: Returns emoji icon (🔴 🟡 🟢)
- `from_string(value: str) -> ContextHealthScore | None`: Parse string to ContextHealthScore
- `default() -> ContextHealthScore`: Returns FAIR (default for new users)

**Usage Example:**

```python
from core.models.enums import ContextHealthScore

# Assess context health
score = ContextHealthScore.GOOD

# Get numeric value for calculations
if score.get_numeric() >= 0.75:
    print("Context is healthy")  # True

# UI display with color/icon
color = score.get_color()  # "#22c55e"
icon = score.get_icon()    # "🟢"
print(f"{icon} Health: {score.value}")  # "🟢 Health: good"

# Parse from string
health = ContextHealthScore.from_string("excellent")  # Returns ContextHealthScore.EXCELLENT
```

**Used By:**
- `UserContextIntelligence` - Overall context health assessment
- Profile hub - Visual health indicators
- Recommendations - Prioritization based on health scores
- Analytics dashboards - Health trends over time

**See:** `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md`, `/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md`

---

### Visibility

Visibility settings for any entity.

Prepares for future multi-user scenarios.

**Valid values:**

- `private` (PRIVATE): Visibility settings for any entity.

Prepares for future multi-user scenarios.
- `shared` (SHARED): Visibility settings for any entity.

Prepares for future multi-user scenarios.
- `team` (TEAM): Visibility settings for any entity.

Prepares for future multi-user scenarios.
- `public` (PUBLIC): Visibility settings for any entity.

Prepares for future multi-user scenarios.

**Methods:**

- `capitalize()`: Return a capitalized version of the string.

More specifically, make the first character have upper case and the rest lower
case.
- `casefold()`: Return a version of the string suitable for caseless comparisons.
- `center()`: Return a centered string of length width.

Padding is done using the specified fill character (default is a space).
- `count()`: S.count(sub[, start[, end]]) -> int

Return the number of non-overlapping occurrences of substring sub in
string S[start:end].  Optional arguments start and end are
interpreted as in slice notation.
- `encode()`: Encode the string using the codec registered for encoding.

encoding
  The encoding in which to encode the string.
errors
  The error handling scheme to use for encoding errors.
  The default is 'strict' meaning that encoding errors raise a
  UnicodeEncodeError.  Other possible values are 'ignore', 'replace' and
  'xmlcharrefreplace' as well as any other name registered with
  codecs.register_error that can handle UnicodeEncodeErrors.
- `endswith()`: S.endswith(suffix[, start[, end]]) -> bool

Return True if S ends with the specified suffix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
suffix can also be a tuple of strings to try.
- `expandtabs()`: Return a copy where all tab characters are expanded using spaces.

If tabsize is not given, a tab size of 8 characters is assumed.
- `find()`: S.find(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `format()`: S.format(*args, **kwargs) -> str

Return a formatted version of S, using substitutions from args and kwargs.
The substitutions are identified by braces ('{' and '}').
- `format_map()`: S.format_map(mapping) -> str

Return a formatted version of S, using substitutions from mapping.
The substitutions are identified by braces ('{' and '}').
- `index()`: S.index(sub[, start[, end]]) -> int

Return the lowest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `isalnum()`: Return True if the string is an alpha-numeric string, False otherwise.

A string is alpha-numeric if all characters in the string are alpha-numeric and
there is at least one character in the string.
- `isalpha()`: Return True if the string is an alphabetic string, False otherwise.

A string is alphabetic if all characters in the string are alphabetic and there
is at least one character in the string.
- `isascii()`: Return True if all characters in the string are ASCII, False otherwise.

ASCII characters have code points in the range U+0000-U+007F.
Empty string is ASCII too.
- `isdecimal()`: Return True if the string is a decimal string, False otherwise.

A string is a decimal string if all characters in the string are decimal and
there is at least one character in the string.
- `isdigit()`: Return True if the string is a digit string, False otherwise.

A string is a digit string if all characters in the string are digits and there
is at least one character in the string.
- `isidentifier()`: Return True if the string is a valid Python identifier, False otherwise.

Call keyword.iskeyword(s) to test whether string s is a reserved identifier,
such as "def" or "class".
- `islower()`: Return True if the string is a lowercase string, False otherwise.

A string is lowercase if all cased characters in the string are lowercase and
there is at least one cased character in the string.
- `isnumeric()`: Return True if the string is a numeric string, False otherwise.

A string is numeric if all characters in the string are numeric and there is at
least one character in the string.
- `isprintable()`: Return True if the string is printable, False otherwise.

A string is printable if all of its characters are considered printable in
repr() or if it is empty.
- `isspace()`: Return True if the string is a whitespace string, False otherwise.

A string is whitespace if all characters in the string are whitespace and there
is at least one character in the string.
- `istitle()`: Return True if the string is a title-cased string, False otherwise.

In a title-cased string, upper- and title-case characters may only
follow uncased characters and lowercase characters only cased ones.
- `isupper()`: Return True if the string is an uppercase string, False otherwise.

A string is uppercase if all cased characters in the string are uppercase and
there is at least one cased character in the string.
- `join()`: Concatenate any number of strings.

The string whose method is called is inserted in between each given string.
The result is returned as a new string.

Example: '.'.join(['ab', 'pq', 'rs']) -> 'ab.pq.rs'
- `ljust()`: Return a left-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `lower()`: Return a copy of the string converted to lowercase.
- `lstrip()`: Return a copy of the string with leading whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `maketrans()`: Return a translation table usable for str.translate().

If there is only one argument, it must be a dictionary mapping Unicode
ordinals (integers) or characters to Unicode ordinals, strings or None.
Character keys will be then converted to ordinals.
If there are two arguments, they must be strings of equal length, and
in the resulting dictionary, each character in x will be mapped to the
character at the same position in y. If there is a third argument, it
must be a string, whose characters will be mapped to None in the result.
- `partition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string.  If the separator is found,
returns a 3-tuple containing the part before the separator, the separator
itself, and the part after it.

If the separator is not found, returns a 3-tuple containing the original string
and two empty strings.
- `removeprefix()`: Return a str with the given prefix string removed if present.

If the string starts with the prefix string, return string[len(prefix):].
Otherwise, return a copy of the original string.
- `removesuffix()`: Return a str with the given suffix string removed if present.

If the string ends with the suffix string and that suffix is not empty,
return string[:-len(suffix)]. Otherwise, return a copy of the original
string.
- `replace()`: Return a copy with all occurrences of substring old replaced by new.

  count
    Maximum number of occurrences to replace.
    -1 (the default value) means replace all occurrences.

If the optional argument count is given, only the first count occurrences are
replaced.
- `rfind()`: S.rfind(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Return -1 on failure.
- `rindex()`: S.rindex(sub[, start[, end]]) -> int

Return the highest index in S where substring sub is found,
such that sub is contained within S[start:end].  Optional
arguments start and end are interpreted as in slice notation.

Raises ValueError when the substring is not found.
- `rjust()`: Return a right-justified string of length width.

Padding is done using the specified fill character (default is a space).
- `rpartition()`: Partition the string into three parts using the given separator.

This will search for the separator in the string, starting at the end. If
the separator is found, returns a 3-tuple containing the part before the
separator, the separator itself, and the part after it.

If the separator is not found, returns a 3-tuple containing two empty strings
and the original string.
- `rsplit()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the end of the string and works to the front.
- `rstrip()`: Return a copy of the string with trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `split()`: Return a list of the substrings in the string, using sep as the separator string.

  sep
    The separator used to split the string.

    When set to None (the default value), will split on any whitespace
    character (including \n \r \t \f and spaces) and will discard
    empty strings from the result.
  maxsplit
    Maximum number of splits.
    -1 (the default value) means no limit.

Splitting starts at the front of the string and works to the end.

Note, str.split() is mainly useful for data that has been intentionally
delimited.  With natural text that includes punctuation, consider using
the regular expression module.
- `splitlines()`: Return a list of the lines in the string, breaking at line boundaries.

Line breaks are not included in the resulting list unless keepends is given and
true.
- `startswith()`: S.startswith(prefix[, start[, end]]) -> bool

Return True if S starts with the specified prefix, False otherwise.
With optional start, test S beginning at that position.
With optional end, stop comparing S at that position.
prefix can also be a tuple of strings to try.
- `strip()`: Return a copy of the string with leading and trailing whitespace removed.

If chars is given and not None, remove characters in chars instead.
- `swapcase()`: Convert uppercase characters to lowercase and lowercase characters to uppercase.
- `title()`: Return a version of the string where each word is titlecased.

More specifically, words start with uppercased characters and all remaining
cased characters have lower case.
- `translate()`: Replace each character in the string using the given translation table.

  table
    Translation table, which must be a mapping of Unicode ordinals to
    Unicode ordinals, strings, or None.

The table must implement lookup/indexing via __getitem__, for instance a
dictionary or list.  If this operation raises LookupError, the character is
left untouched.  Characters mapped to None are deleted.
- `upper()`: Return a copy of the string converted to uppercase.
- `zfill()`: Pad a numeric string with zeros on the left, to fill a field of the given width.

The string is never truncated.

**Example:**
```python
from core.models.enums import Visibility

# Using enum value
status = Visibility.PRIVATE
print(status.value)  # "private"

# Using dynamic method
result = status.capitalize()
print(result)
```

---

## Usage Guidelines

### Importing Enums
```python
from core.models.enums import Priority, KuStatus, Domain
```

### Using Enum Values
```python
# Access by name
priority = Priority.HIGH

# Access by value
priority = Priority('high')

# Get string value
print(priority.value)  # 'high'

# Get member name
print(priority.name)   # 'HIGH'
```

### Dynamic Enum Methods

Many enums include dynamic methods for UI rendering and behavior:

```python
# Get UI color
color = Priority.HIGH.get_color()  # '#F59E0B'

# Convert to numeric
num = Priority.HIGH.to_numeric()   # 3

# Check state
is_done = KuStatus.COMPLETED.is_terminal()  # True
```

### Validation in Pydantic Models

Enums automatically validate in Pydantic models:

```python
from pydantic import BaseModel
from core.models.enums import Priority

class Task(BaseModel):
    title: str
    priority: Priority  # Only accepts valid Priority values

# Valid
task = Task(title='Review', priority=Priority.HIGH)
task = Task(title='Review', priority='high')  # Also works

# Invalid - raises ValidationError
task = Task(title='Review', priority='invalid')
```

## Best Practices

1. **Single Source of Truth**: Always import from `core/models/enums/`, never duplicate enum definitions
2. **Use Dynamic Methods**: Leverage enum methods (`.get_color()`, `.to_numeric()`) instead of hardcoded dictionaries
3. **Type Hints**: Always use enum types in function signatures for better IDE support
4. **Comparison**: Use enum members directly for comparison (`status == KuStatus.COMPLETED`)
5. **Serialization**: Use `.value` when serializing to JSON/YAML

## Adding New Enums

When adding new enums to `core/models/enums/`:

1. Define the enum class with descriptive docstring
2. Use `str, Enum` for string-based enums (most common)
3. Add dynamic methods for UI/behavior (`.get_color()`, `.to_numeric()`, etc.)
4. Document the enum's purpose and which domains use it
5. Run this script to update documentation: `poetry run python scripts/generate_enum_docs.py`

---

*Documentation auto-generated by `scripts/generate_enum_docs.py`*
*Total enums documented: 35*