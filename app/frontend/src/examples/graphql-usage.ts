/**
 * TypeScript GraphQL Usage Examples
 * ==================================
 *
 * Examples of using auto-generated TypeScript types with SKUEL GraphQL API.
 */

import { gql } from '@apollo/client';
// Import generated types (after running npm run codegen)
// import {
//   GetTasksQuery,
//   GetTasksQueryVariables,
//   KnowledgeNode,
//   Task,
//   CreateTaskMutation,
//   CreateTaskMutationVariables
// } from '../generated/graphql';

// ============================================================================
// Example 1: Query with Type Safety
// ============================================================================

export const GET_TASKS = gql`
  query GetTasks($userUid: String!, $limit: Int, $includeCompleted: Boolean) {
    tasks(userUid: $userUid, limit: $limit, includeCompleted: $includeCompleted) {
      uid
      title
      description
      status
      priority
      knowledge {
        uid
        title
        domain
        tags
      }
    }
  }
`;

// Usage with Apollo Client (example)
// const { data, loading, error } = useQuery<GetTasksQuery, GetTasksQueryVariables>(
//   GET_TASKS,
//   {
//     variables: {
//       userUid: "user.001",
//       limit: 10,
//       includeCompleted: false
//     }
//   }
// );
//
// if (data) {
//   // TypeScript knows exact shape of data.tasks
//   data.tasks.forEach(task => {
//     console.log(task.title);           // ✅ Autocomplete works!
//     console.log(task.knowledge?.title); // ✅ Optional chaining safe
//   });
// }

// ============================================================================
// Example 2: Nested Query with Prerequisites
// ============================================================================

export const GET_KNOWLEDGE_WITH_PREREQUISITES = gql`
  query GetKnowledgeWithPrerequisites($uid: String!) {
    knowledgeUnit(uid: $uid) {
      uid
      title
      summary
      domain
      tags
      qualityScore
      prerequisites {
        uid
        title
        domain
        prerequisites {
          uid
          title
        }
      }
      enables {
        uid
        title
        domain
      }
    }
  }
`;

// Usage example:
// const { data } = useQuery<GetKnowledgeWithPrerequisitesQuery>(
//   GET_KNOWLEDGE_WITH_PREREQUISITES,
//   { variables: { uid: "ku.python.functions" } }
// );
//
// if (data?.knowledgeUnit) {
//   const ku = data.knowledgeUnit;
//
//   // Nested prerequisites are fully typed
//   ku.prerequisites.forEach(prereq => {
//     console.log(`Prerequisite: ${prereq.title}`);
//
//     // Even nested prerequisites have types
//     prereq.prerequisites.forEach(subPrereq => {
//       console.log(`  Sub-prerequisite: ${subPrereq.title}`);
//     });
//   });
// }

// ============================================================================
// Example 3: Mutation with Type Safety
// ============================================================================

export const CREATE_TASK = gql`
  mutation CreateTask($input: TaskInput!) {
    createTask(input: $input) {
      uid
      title
      description
      status
      priority
      knowledge {
        uid
        title
      }
    }
  }
`;

// Usage example:
// const [createTask, { loading }] = useMutation<CreateTaskMutation, CreateTaskMutationVariables>(
//   CREATE_TASK
// );
//
// const handleCreateTask = async () => {
//   const result = await createTask({
//     variables: {
//       input: {
//         title: "Learn GraphQL",
//         description: "Study GraphQL fundamentals",
//         priority: "high",
//         knowledgeUid: "ku.graphql.basics"
//       }
//     }
//   });
//
//   if (result.data?.createTask) {
//     console.log(`Created task: ${result.data.createTask.uid}`);
//   }
// };

// ============================================================================
// Example 4: Cross-Domain Discovery Query
// ============================================================================

export const DISCOVER_CROSS_DOMAIN = gql`
  query DiscoverCrossDomain(
    $userKnowledge: [String!]!
    $targetDomains: [String!]
    $maxOpportunities: Int
  ) {
    discoverCrossDomain(
      userKnowledge: $userKnowledge
      targetDomains: $targetDomains
      maxOpportunities: $maxOpportunities
    ) {
      source {
        uid
        title
        domain
      }
      target {
        uid
        title
        domain
      }
      bridgeType
      transferability
      effortRequired
      reasoning
      practicalProjects
      successPatterns
      supportingExamples
    }
  }
`;

// Usage example:
// const { data } = useQuery<DiscoverCrossDomainQuery, DiscoverCrossDomainQueryVariables>(
//   DISCOVER_CROSS_DOMAIN,
//   {
//     variables: {
//       userKnowledge: ["python", "algorithms", "data_structures"],
//       targetDomains: ["BUSINESS", "TECH"],
//       maxOpportunities: 5
//     }
//   }
// );
//
// if (data?.discoverCrossDomain) {
//   data.discoverCrossDomain.forEach(opportunity => {
//     console.log(`Cross-domain opportunity: ${opportunity.bridgeType}`);
//     console.log(`From ${opportunity.source.domain} to ${opportunity.target.domain}`);
//     console.log(`Transferability: ${opportunity.transferability}`);
//
//     // Optional fields are properly typed
//     if (opportunity.practicalProjects) {
//       console.log(`Projects: ${opportunity.practicalProjects.join(', ')}`);
//     }
//   });
// }

// ============================================================================
// Example 5: Dashboard Query (Complex Nested Query)
// ============================================================================

export const GET_USER_DASHBOARD = gql`
  query GetUserDashboard($userUid: String) {
    userDashboard(userUid: $userUid) {
      tasksCount
      pathsCount
      habitsCount
    }
  }
`;

// Usage example:
// const { data } = useQuery<GetUserDashboardQuery, GetUserDashboardQueryVariables>(
//   GET_USER_DASHBOARD,
//   { variables: { userUid: "user.001" } }
// );
//
// if (data?.userDashboard) {
//   const stats = data.userDashboard;
//   console.log(`Tasks: ${stats.tasksCount}`);
//   console.log(`Paths: ${stats.pathsCount}`);
//   console.log(`Habits: ${stats.habitsCount}`);
// }

// ============================================================================
// Example 6: Search Query with Filters
// ============================================================================

export const SEARCH_KNOWLEDGE = gql`
  query SearchKnowledge($input: SearchInput!) {
    searchKnowledge(input: $input) {
      knowledge {
        uid
        title
        summary
        domain
        tags
        qualityScore
      }
      relevance
      explanation
    }
  }
`;

// Usage example:
// const { data } = useQuery<SearchKnowledgeQuery, SearchKnowledgeQueryVariables>(
//   SEARCH_KNOWLEDGE,
//   {
//     variables: {
//       input: {
//         query: "machine learning",
//         limit: 10,
//         domains: ["TECH", "BUSINESS"],
//         minQuality: 0.7
//       }
//     }
//   }
// );
//
// if (data?.searchKnowledge) {
//   data.searchKnowledge.forEach(result => {
//     console.log(`${result.knowledge.title} (relevance: ${result.relevance})`);
//     console.log(`  ${result.explanation}`);
//   });
// }

// ============================================================================
// Type Guards and Utility Functions
// ============================================================================

// Type guard for checking if a task has knowledge
// export function taskHasKnowledge(task: Task): task is Task & { knowledge: KnowledgeNode } {
//   return task.knowledge !== null && task.knowledge !== undefined;
// }

// Usage:
// tasks.filter(taskHasKnowledge).forEach(task => {
//   // TypeScript knows task.knowledge is defined here
//   console.log(task.knowledge.title);
// });

// ============================================================================
// Benefits of Generated Types
// ============================================================================

/*
✅ Full Type Safety
   - No runtime type errors
   - Catch mismatches at compile time

✅ IDE Autocomplete
   - IntelliSense for all GraphQL fields
   - Discover available fields without docs

✅ Refactoring Safety
   - Rename fields in schema → TypeScript errors show all affected code
   - Impossible to use deprecated fields

✅ Self-Documenting Code
   - Types serve as inline documentation
   - No need to guess field types

✅ Better Developer Experience
   - Faster development
   - Fewer bugs
   - Easier onboarding for new developers
*/
