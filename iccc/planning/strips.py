"""STRIPS planner with A* search for task planning."""

import heapq
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class State:
    """Represents a state in the planning problem."""

    facts: frozenset[str]

    def __hash__(self) -> int:
        return hash(self.facts)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, State):
            return False
        return self.facts == other.facts

    def satisfies(self, preconditions: set[str]) -> bool:
        """Check if this state satisfies given preconditions."""
        return preconditions.issubset(self.facts)

    def apply_action(self, action: "Action") -> "State":
        """Apply an action to this state, producing a new state."""
        new_facts = set(self.facts)
        new_facts -= action.delete_effects
        new_facts |= action.add_effects
        return State(frozenset(new_facts))


@dataclass
class Action:
    """Represents an action in STRIPS."""

    name: str
    preconditions: set[str]
    add_effects: set[str]
    delete_effects: set[str]
    cost: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_applicable(self, state: State) -> bool:
        """Check if this action can be applied in the given state."""
        return state.satisfies(self.preconditions)

    def __repr__(self) -> str:
        return f"Action({self.name})"


@dataclass
class PlanNode:
    """Node in the A* search tree."""

    state: State
    g_cost: float  # Cost from start
    h_cost: float  # Heuristic cost to goal
    parent: Optional["PlanNode"] = None
    action: Optional[Action] = None

    @property
    def f_cost(self) -> float:
        """Total estimated cost (f = g + h)."""
        return self.g_cost + self.h_cost

    def __lt__(self, other: "PlanNode") -> bool:
        return self.f_cost < other.f_cost


class STRIPSPlanner:
    """STRIPS planner using A* search."""

    def __init__(self, heuristic: Optional[Callable[[State, State], float]] = None) -> None:
        """
        Initialize planner.

        Args:
            heuristic: Heuristic function h(state, goal) -> float
                      Defaults to goal counting heuristic
        """
        self.heuristic = heuristic or self._goal_counting_heuristic

    def plan(
        self,
        initial_state: State,
        goal_state: State,
        actions: list[Action],
        max_iterations: int = 1000,
    ) -> Optional[list[Action]]:
        """
        Find a plan from initial state to goal state.

        Args:
            initial_state: Starting state
            goal_state: Desired goal state
            actions: Available actions
            max_iterations: Maximum search iterations

        Returns:
            List of actions to reach goal, or None if no plan found
        """
        # Check if already at goal
        if initial_state.satisfies(goal_state.facts):
            return []

        # A* search
        start_node = PlanNode(
            state=initial_state,
            g_cost=0.0,
            h_cost=self.heuristic(initial_state, goal_state),
        )

        open_set: list[PlanNode] = [start_node]
        closed_set: set[State] = set()
        iterations = 0

        while open_set and iterations < max_iterations:
            iterations += 1

            # Pop node with lowest f_cost
            current_node = heapq.heappop(open_set)

            # Check if goal reached
            if current_node.state.satisfies(goal_state.facts):
                return self._reconstruct_plan(current_node)

            # Skip if already visited
            if current_node.state in closed_set:
                continue

            closed_set.add(current_node.state)

            # Expand node
            for action in actions:
                if not action.is_applicable(current_node.state):
                    continue

                # Apply action
                new_state = current_node.state.apply_action(action)

                # Skip if already visited
                if new_state in closed_set:
                    continue

                # Create child node
                g_cost = current_node.g_cost + action.cost
                h_cost = self.heuristic(new_state, goal_state)

                child_node = PlanNode(
                    state=new_state,
                    g_cost=g_cost,
                    h_cost=h_cost,
                    parent=current_node,
                    action=action,
                )

                heapq.heappush(open_set, child_node)

        # No plan found
        return None

    def _reconstruct_plan(self, goal_node: PlanNode) -> list[Action]:
        """Reconstruct the plan by backtracking from goal node."""
        plan = []
        current = goal_node

        while current.parent is not None:
            if current.action:
                plan.append(current.action)
            current = current.parent

        return list(reversed(plan))

    @staticmethod
    def _goal_counting_heuristic(state: State, goal_state: State) -> float:
        """
        Simple heuristic: count unsatisfied goals.

        This is admissible (never overestimates) because each action
        can add at most one goal fact.
        """
        unsatisfied_goals = goal_state.facts - state.facts
        return float(len(unsatisfied_goals))

    @staticmethod
    def create_software_dev_actions() -> list[Action]:
        """
        Create common software development actions.

        Returns:
            List of predefined actions for software tasks
        """
        return [
            # File operations
            Action(
                name="read_file",
                preconditions={"file_exists"},
                add_effects={"file_content_known"},
                delete_effects=set(),
                cost=1.0,
            ),
            Action(
                name="write_file",
                preconditions={"file_content_known"},
                add_effects={"file_exists", "file_modified"},
                delete_effects=set(),
                cost=2.0,
            ),
            Action(
                name="create_file",
                preconditions=set(),
                add_effects={"file_exists"},
                delete_effects=set(),
                cost=1.5,
            ),
            # Code operations
            Action(
                name="write_function",
                preconditions={"file_exists", "function_design_known"},
                add_effects={"function_exists", "code_written"},
                delete_effects=set(),
                cost=5.0,
            ),
            Action(
                name="write_test",
                preconditions={"function_exists"},
                add_effects={"test_exists"},
                delete_effects=set(),
                cost=3.0,
            ),
            Action(
                name="run_test",
                preconditions={"test_exists", "function_exists"},
                add_effects={"test_passed"},
                delete_effects=set(),
                cost=2.0,
            ),
            Action(
                name="refactor_code",
                preconditions={"function_exists", "test_passed"},
                add_effects={"code_refactored"},
                delete_effects=set(),
                cost=4.0,
            ),
            # Design operations
            Action(
                name="design_function",
                preconditions={"requirements_known"},
                add_effects={"function_design_known"},
                delete_effects=set(),
                cost=3.0,
            ),
            Action(
                name="design_architecture",
                preconditions={"requirements_known"},
                add_effects={"architecture_designed"},
                delete_effects=set(),
                cost=6.0,
            ),
            # Documentation
            Action(
                name="write_docstring",
                preconditions={"function_exists"},
                add_effects={"function_documented"},
                delete_effects=set(),
                cost=1.5,
            ),
            Action(
                name="write_readme",
                preconditions={"code_written"},
                add_effects={"readme_exists"},
                delete_effects=set(),
                cost=3.0,
            ),
        ]
