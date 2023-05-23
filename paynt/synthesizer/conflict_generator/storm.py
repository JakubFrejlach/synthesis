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

        # Store simple holes occurence statistics
        self.simple_holes_stats = {}

    def construct_conflicts(
        self, family, assignment, dtmc, conflict_requests, accepting_assignment
    ):

        self.counterexample_generator.prepare_dtmc(dtmc.model, dtmc.quotient_state_map)

        simple_holes = [
            hole_index
            for hole_index in family.hole_indices
            if family.mdp.hole_simple[hole_index]
        ]

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

            # Log occurence of each simple hole
            for hole in conflict:
                if hole in simple_holes:
                    if hole not in self.simple_holes_stats:
                        self.simple_holes_stats[hole] = 1
                    else:
                        self.simple_holes_stats[hole] += 1

            conflicts.append(conflict)

        return conflicts, accepting_assignment
