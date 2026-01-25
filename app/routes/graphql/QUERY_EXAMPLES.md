# SKUEL GraphQL Query Examples
## Phase 3: Leveraging GraphQL for Complex Reads

This document demonstrates GraphQL's advantages over REST for complex, nested queries in SKUEL's knowledge graph.

---

## 1. Nested Data Queries (Single Request)

### Example: Full Learning Path with Nested Steps and Knowledge

**GraphQL Query (1 Request):**
```graphql
query GetLearningPathFull {
  learning_path(uid: "lp.python_mastery") {
    uid
    name
    goal
    estimated_hours
    total_steps
    steps {
      step_number
      mastery_threshold
      estimated_time
      knowledge {
        uid
        title
        summary
        domain
        quality_score
        prerequisites {
          uid
          title
          summary
        }
        enables {
          uid
          title
          summary
        }
      }
    }
  }
}
```

**Equivalent REST Calls (4+ Requests):**
```bash
# 1. Get learning path
GET /api/learning?uid=lp.python_mastery

# 2. Get learning steps
GET /api/learning/lp.python_mastery/steps

# 3. For EACH step, get knowledge unit (N requests)
GET /api/knowledge?uid=ku.python_basics
GET /api/knowledge?uid=ku.python_functions
GET /api/knowledge?uid=ku.python_classes
# ... (one per step)

# 4. For EACH knowledge unit, get prerequisites (N requests)
GET /api/knowledge/ku.python_basics/prerequisites
GET /api/knowledge/ku.python_functions/prerequisites
# ... (one per KU)

# 5. For EACH knowledge unit, get enabled concepts (N requests)
GET /api/knowledge/ku.python_basics/dependencies
# ... (one per KU)

# TOTAL: 1 + 1 + N + N + N = 1 + 1 + 3N requests
# For 10 steps: 32 REST calls vs 1 GraphQL query!
```

**GraphQL Response:**
```json
{
  "data": {
    "learning_path": {
      "uid": "lp.python_mastery",
      "name": "Python Mastery",
      "goal": "Master Python programming from basics to advanced concepts",
      "estimated_hours": 40.0,
      "total_steps": 8,
      "steps": [
        {
          "step_number": 1,
          "mastery_threshold": 0.8,
          "estimated_time": 4.0,
          "knowledge": {
            "uid": "ku.python_basics",
            "title": "Python Fundamentals",
            "summary": "Variables, data types, control flow",
            "domain": "tech",
            "quality_score": 0.95,
            "prerequisites": [],
            "enables": [
              {
                "uid": "ku.python_functions",
                "title": "Python Functions",
                "summary": "Defining and using functions"
              }
            ]
          }
        },
        {
          "step_number": 2,
          "mastery_threshold": 0.75,
          "estimated_time": 5.0,
          "knowledge": {
            "uid": "ku.python_functions",
            "title": "Python Functions",
            "summary": "Defining and using functions, parameters, returns",
            "domain": "tech",
            "quality_score": 0.92,
            "prerequisites": [
              {
                "uid": "ku.python_basics",
                "title": "Python Fundamentals",
                "summary": "Variables, data types, control flow"
              }
            ],
            "enables": [
              {
                "uid": "ku.python_classes",
                "title": "Python Classes",
                "summary": "Object-oriented programming"
              }
            ]
          }
        }
      ]
    }
  }
}
```

---

## 2. Graph Traversal Queries

### Example: Prerequisite Chain with Full Dependency Tree

**GraphQL Query:**
```graphql
query GetPrerequisiteChain {
  prerequisite_chain(
    knowledge_uid: "ku.machine_learning"
    max_depth: 5
    user_uid: "user.mike"
  ) {
    target {
      uid
      title
      summary
      domain
    }
    total_prerequisites
    prerequisites_mastered
    estimated_total_hours
    prerequisite_tree {
      knowledge {
        uid
        title
        summary
        quality_score
      }
      depth
      is_mastered
      children {
        knowledge {
          uid
          title
        }
        depth
        is_mastered
        children {
          knowledge {
            uid
            title
          }
          depth
          is_mastered
        }
      }
    }
  }
}
```

**Example Response:**
```json
{
  "data": {
    "prerequisite_chain": {
      "target": {
        "uid": "ku.machine_learning",
        "title": "Introduction to Machine Learning",
        "summary": "Core ML concepts, algorithms, and applications",
        "domain": "tech"
      },
      "total_prerequisites": 5,
      "prerequisites_mastered": 2,
      "estimated_total_hours": 12.0,
      "prerequisite_tree": [
        {
          "knowledge": {
            "uid": "ku.linear_algebra",
            "title": "Linear Algebra Fundamentals",
            "summary": "Vectors, matrices, transformations",
            "quality_score": 0.93
          },
          "depth": 1,
          "is_mastered": true,
          "children": [
            {
              "knowledge": {
                "uid": "ku.calculus_basics",
                "title": "Calculus Fundamentals"
              },
              "depth": 2,
              "is_mastered": false,
              "children": []
            }
          ]
        },
        {
          "knowledge": {
            "uid": "ku.python_advanced",
            "title": "Advanced Python Programming",
            "summary": "NumPy, data structures, algorithms",
            "quality_score": 0.89
          },
          "depth": 1,
          "is_mastered": true,
          "children": [
            {
              "knowledge": {
                "uid": "ku.python_basics",
                "title": "Python Fundamentals"
              },
              "depth": 2,
              "is_mastered": true,
              "children": []
            }
          ]
        }
      ]
    }
  }
}
```

**Why This is Powerful:**
- Single query traverses entire prerequisite tree
- Shows mastery status at each level
- Calculates total learning hours
- Identifies knowledge gaps (unmastered prerequisites)
- REST would require recursive requests for each level

---

### Example: Knowledge Dependency Graph

**GraphQL Query:**
```graphql
query GetKnowledgeDependencies {
  knowledge_dependencies(
    knowledge_uid: "ku.rest_api_design"
    depth: 2
  ) {
    center {
      uid
      title
      domain
    }
    depth
    nodes {
      uid
      title
      domain
      quality_score
    }
    edges {
      from_knowledge {
        uid
        title
      }
      to_knowledge {
        uid
        title
      }
      relationship_type
      strength
    }
  }
}
```

**Example Response:**
```json
{
  "data": {
    "knowledge_dependencies": {
      "center": {
        "uid": "ku.rest_api_design",
        "title": "RESTful API Design",
        "domain": "tech"
      },
      "depth": 2,
      "nodes": [
        {
          "uid": "ku.rest_api_design",
          "title": "RESTful API Design",
          "domain": "tech",
          "quality_score": 0.91
        },
        {
          "uid": "ku.http_protocol",
          "title": "HTTP Protocol Fundamentals",
          "domain": "tech",
          "quality_score": 0.95
        },
        {
          "uid": "ku.json_data_format",
          "title": "JSON Data Format",
          "domain": "tech",
          "quality_score": 0.88
        },
        {
          "uid": "ku.microservices",
          "title": "Microservices Architecture",
          "domain": "tech",
          "quality_score": 0.87
        },
        {
          "uid": "ku.graphql_basics",
          "title": "GraphQL Fundamentals",
          "domain": "tech",
          "quality_score": 0.89
        }
      ],
      "edges": [
        {
          "from_knowledge": {
            "uid": "ku.http_protocol",
            "title": "HTTP Protocol Fundamentals"
          },
          "to_knowledge": {
            "uid": "ku.rest_api_design",
            "title": "RESTful API Design"
          },
          "relationship_type": "REQUIRES",
          "strength": 1.0
        },
        {
          "from_knowledge": {
            "uid": "ku.json_data_format",
            "title": "JSON Data Format"
          },
          "to_knowledge": {
            "uid": "ku.rest_api_design",
            "title": "RESTful API Design"
          },
          "relationship_type": "REQUIRES",
          "strength": 1.0
        },
        {
          "from_knowledge": {
            "uid": "ku.rest_api_design",
            "title": "RESTful API Design"
          },
          "to_knowledge": {
            "uid": "ku.microservices",
            "title": "Microservices Architecture"
          },
          "relationship_type": "ENABLES",
          "strength": 1.0
        },
        {
          "from_knowledge": {
            "uid": "ku.rest_api_design",
            "title": "RESTful API Design"
          },
          "to_knowledge": {
            "uid": "ku.graphql_basics",
            "title": "GraphQL Fundamentals"
          },
          "relationship_type": "ENABLES",
          "strength": 1.0
        }
      ]
    }
  }
}
```

**Use Case:** Perfect for visualizing knowledge maps, concept relationships, learning paths

---

## 3. Flexible Field Selection

### Mobile Client - Minimal Data (Bandwidth-Conscious)

**GraphQL Query:**
```graphql
query GetLearningPathsLight {
  learning_paths(limit: 10) {
    uid
    name
    total_steps
  }
}
```

**Response (Minimal):**
```json
{
  "data": {
    "learning_paths": [
      {
        "uid": "lp.python_mastery",
        "name": "Python Mastery",
        "total_steps": 8
      },
      {
        "uid": "lp.web_development",
        "name": "Full-Stack Web Development",
        "total_steps": 15
      }
    ]
  }
}
```

**Payload Size:** ~250 bytes

---

### Web Dashboard - Rich Data (Full Experience)

**GraphQL Query:**
```graphql
query GetLearningPathsRich {
  learning_paths(limit: 10) {
    uid
    name
    goal
    estimated_hours
    total_steps
    steps {
      step_number
      knowledge {
        uid
        title
        summary
        quality_score
        domain
      }
    }
  }
}
```

**Response (Rich):**
```json
{
  "data": {
    "learning_paths": [
      {
        "uid": "lp.python_mastery",
        "name": "Python Mastery",
        "goal": "Master Python programming from basics to advanced concepts",
        "estimated_hours": 40.0,
        "total_steps": 8,
        "steps": [
          {
            "step_number": 1,
            "knowledge": {
              "uid": "ku.python_basics",
              "title": "Python Fundamentals",
              "summary": "Variables, data types, control flow",
              "quality_score": 0.95,
              "domain": "tech"
            }
          }
        ]
      }
    ]
  }
}
```

**Payload Size:** ~2.5 KB

**Key Advantage:** Same endpoint, clients control payload size. No over-fetching, no under-fetching.

---

## 4. Learning Path Context (Single Query Replaces 5+ REST Calls)

**GraphQL Query:**
```graphql
query GetLearningPathContext {
  learning_path_with_context(
    path_uid: "lp.data_science"
    user_uid: "user.mike"
  ) {
    path {
      uid
      name
      goal
      total_steps
      estimated_hours
    }
    current_step_number
    completed_steps
    completion_percentage
    prerequisites_met
    blockers {
      blocker_type
      knowledge_uid
      knowledge_title
      severity
      description
      recommended_action
    }
    next_recommended_steps {
      step_number
      knowledge_uid
      mastery_threshold
      estimated_time
      knowledge {
        uid
        title
        summary
        prerequisites {
          uid
          title
        }
      }
    }
  }
}
```

**Equivalent REST Calls:**
```bash
# 1. Get learning path
GET /api/learning?uid=lp.data_science

# 2. Get user progress
GET /api/progress?user_uid=user.mike&path_uid=lp.data_science

# 3. Get path steps
GET /api/learning/lp.data_science/steps

# 4. Get blockers (check prerequisites for each step)
GET /api/learning/lp.data_science/blockers?user_uid=user.mike

# 5. Get recommended next steps
GET /api/learning/lp.data_science/recommendations?user_uid=user.mike

# 6. For each recommended step, get knowledge details
GET /api/knowledge?uid=ku.statistics_basics
GET /api/knowledge?uid=ku.pandas_intro

# TOTAL: 5+ core requests + N requests for knowledge details
```

**Example Response:**
```json
{
  "data": {
    "learning_path_with_context": {
      "path": {
        "uid": "lp.data_science",
        "name": "Data Science Fundamentals",
        "goal": "Learn data science from Python basics to ML models",
        "total_steps": 12,
        "estimated_hours": 60.0
      },
      "current_step_number": 5,
      "completed_steps": 4,
      "completion_percentage": 33.33,
      "prerequisites_met": false,
      "blockers": [
        {
          "blocker_type": "missing_prerequisite",
          "knowledge_uid": "ku.statistics_basics",
          "knowledge_title": "Statistics Fundamentals",
          "severity": "warning",
          "description": "2 prerequisite(s) not yet mastered",
          "recommended_action": "Complete prerequisites before attempting Statistics Fundamentals"
        }
      ],
      "next_recommended_steps": [
        {
          "step_number": 5,
          "knowledge_uid": "ku.statistics_basics",
          "mastery_threshold": 0.75,
          "estimated_time": 6.0,
          "knowledge": {
            "uid": "ku.statistics_basics",
            "title": "Statistics Fundamentals",
            "summary": "Mean, median, distributions, probability",
            "prerequisites": [
              {
                "uid": "ku.python_basics",
                "title": "Python Fundamentals"
              },
              {
                "uid": "ku.mathematics_basics",
                "title": "Basic Mathematics"
              }
            ]
          }
        }
      ]
    }
  }
}
```

---

## 5. Learning Path Blockers Analysis

**GraphQL Query:**
```graphql
query GetPathBlockers {
  learning_path_blockers(
    path_uid: "lp.machine_learning"
    user_uid: "user.mike"
  ) {
    blocker_type
    knowledge_uid
    knowledge_title
    severity
    description
    recommended_action
  }
}
```

**Example Response:**
```json
{
  "data": {
    "learning_path_blockers": [
      {
        "blocker_type": "missing_prerequisite",
        "knowledge_uid": "ku.linear_algebra",
        "knowledge_title": "Linear Algebra Fundamentals",
        "severity": "critical",
        "description": "5 prerequisite(s) not yet mastered",
        "recommended_action": "Complete Linear Algebra before attempting ML algorithms"
      },
      {
        "blocker_type": "missing_content",
        "knowledge_uid": "ku.deleted_concept",
        "knowledge_title": "Step 8",
        "severity": "critical",
        "description": "Knowledge unit ku.deleted_concept does not exist",
        "recommended_action": "Remove this step or replace with valid knowledge unit"
      }
    ]
  }
}
```

**Use Case:** Pre-flight check before starting a learning path - identify all issues upfront

---

## 6. Combined Dashboard Query (Ultimate GraphQL Demo)

**GraphQL Query:**
```graphql
query GetUserDashboardComplete {
  user_dashboard {
    tasks_count
    paths_count
    habits_count
  }

  learning_paths(limit: 5) {
    uid
    name
    total_steps
    estimated_hours
  }

  tasks(limit: 10, include_completed: false) {
    uid
    title
    priority
    status
    knowledge {
      uid
      title
      domain
    }
  }

  discover_cross_domain(
    user_knowledge: ["ku.python_basics", "ku.yoga_basics"]
    max_opportunities: 5
  ) {
    source {
      title
      domain
    }
    target {
      title
      domain
    }
    bridgeType
    transferability
    reasoning
  }
}
```

**Equivalent REST:**
```bash
# 8+ separate API calls
GET /api/dashboard/summary
GET /api/learning?limit=5
GET /api/tasks?limit=10&status=incomplete
GET /api/knowledge?uid=ku_1  # For each task
GET /api/knowledge?uid=ku_2
# ...
GET /api/cross-domain/discover
```

**GraphQL Advantage:** Everything in ONE round-trip, client controls exact data shape.

---

## Performance Comparison

| Operation | REST API | GraphQL | Improvement |
|-----------|----------|---------|-------------|
| Get learning path with steps | 2-12 requests | 1 request | **6x fewer** |
| Full path + knowledge + prerequisites | 32+ requests | 1 request | **32x fewer** |
| Prerequisite chain (5 levels) | 15+ requests | 1 request | **15x fewer** |
| Dashboard with tasks/paths/habits | 8+ requests | 1 request | **8x fewer** |
| Mobile list (minimal data) | Full payload | Custom fields | **90% less data** |

---

## Testing These Queries

**Using curl:**
```bash
curl -X POST http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { learning_paths(limit: 5) { uid name total_steps } }"
  }'
```

**Using GraphQL Playground:**
1. Navigate to `http://localhost:8000/graphql`
2. Paste any query from above
3. Click "Play" button
4. Explore schema with Ctrl+Space autocomplete

---

## Best Practices

### ✅ DO:
- Request only fields you need
- Use fragments for repeated field sets
- Leverage nested queries to eliminate multiple requests
- Use query depth limits to prevent abuse

### ❌ DON'T:
- Request all fields if you only need a few
- Make multiple GraphQL queries when one nested query works
- Use mutations (use REST API instead per hybrid approach)
- Exceed depth limits (max 5 for most queries)

---

## Next Steps

1. **Try these queries** against your local SKUEL instance
2. **Measure performance** - compare REST vs GraphQL
3. **Build UI components** that leverage these queries
4. **Extend with real data** - connect to actual progress tracking
5. **Add more graph queries** - customize for your use cases

---

**GraphQL at SKUEL**: Read-only queries for complex graph traversal. Use REST for mutations. Best of both worlds.
