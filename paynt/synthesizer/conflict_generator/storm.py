import logging

import stormpy.synthesis

logger = logging.getLogger(__name__)


class ConflictGeneratorStorm:
    def __init__(self, quotient):
        self.quotient = quotient
        self.counterexample_generator = None

    @property
    def name(self):
        return "(Storm)"

    def initialize(self):
        quotient_relevant_holes = self.quotient.coloring.state_to_holes
        formulae = self.quotient.specification.stormpy_formulae()
        self.counterexample_generator = stormpy.synthesis.CounterexampleGenerator(
            self.quotient.quotient_mdp,
            self.quotient.design_space.num_holes,
            quotient_relevant_holes,
            formulae,
        )

    def construct_conflicts(
        self, family, assignment, dtmc, conflict_requests, accepting_assignment
    ):

        self.counterexample_generator.prepare_dtmc(dtmc.model, dtmc.quotient_state_map)

        conflicts = []
        for request in conflict_requests:
            index, prop, _, family_result = request

            threshold = prop.threshold

            bounds = None
            scheduler_selection = None
            if family_result is not None:
                bounds = family_result.primary.result

            conflict = self.counterexample_generator.construct_conflict(
                index, threshold, bounds, family.mdp.quotient_state_map
            )
            conflicts.append(conflict)

        return conflicts, accepting_assignment
