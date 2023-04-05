import logging

import stormpy.synthesis
from paynt.quotient.property import OptimalityProperty

logger = logging.getLogger(__name__)


class ConflictGeneratorDtmcMdp:
    def __init__(self, quotient):
        self.quotient = quotient
        self.counterexample_generator = None

    @property
    def name(self):
        return "(Storm - MDP + DTMC)"

    def initialize(self):
        quotient_relevant_holes = self.quotient.coloring.state_to_holes
        formulae = self.quotient.specification.stormpy_formulae()
        self.counterexample_generator = stormpy.synthesis.CounterexampleGenerator(
            self.quotient.quotient_mdp,
            self.quotient.design_space.num_holes,
            quotient_relevant_holes,
            formulae,
        )

        self.counterexample_generator_mdp = (
            stormpy.synthesis.CounterexampleGeneratorMdp(
                self.quotient.quotient_mdp,
                self.quotient.design_space.num_holes,
                quotient_relevant_holes,
                formulae,
            )
        )

    def construct_conflicts(
        self, family, assignment, dtmc, conflict_requests, accepting_assignment
    ):
        assert (
            len(conflict_requests) == 1
        ), "we don't know how to handle multiple conflict requests in this mode, consider CEGIS in another mode"

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

        # generalize simple holes, i.e. starting from the full family, fix each
        # non-simple hole to the option selected by the assignment
        subfamily = family.copy()
        simple_holes = [
            hole_index
            for hole_index in subfamily.hole_indices
            if family.mdp.hole_simple[hole_index]
        ]
        non_simple_holes = [
            hole_index
            for hole_index in subfamily.hole_indices
            if not family.mdp.hole_simple[hole_index]
        ]
        for hole_index in non_simple_holes:
            subfamily.assume_hole_options(hole_index, assignment[hole_index].options)
        self.quotient.build(subfamily)
        submdp = subfamily.mdp

        index, prop, _, family_result = conflict_requests[0]

        # check primary direction
        primary = submdp.model_check_property(prop)
        if primary.sat:
            # found satisfying assignment
            selection, _, _, _, consistent = self.quotient.scheduler_consistent(
                submdp, prop, primary.result
            )
            assert consistent
            if isinstance(prop, OptimalityProperty):
                self.quotient.specification.optimality.update_optimum(primary.value)
            accepting_assignment = family.copy()
            for hole_index in family.hole_indices:
                accepting_assignment.assume_hole_options(
                    hole_index, selection[hole_index]
                )

        # Bit vector of hole relevancy, 0 = non simple hole, 1 = simple hole
        simple_holes_bit_vector = stormpy.storage.BitVector(
            len(non_simple_holes) + len(simple_holes), simple_holes
        )

        self.counterexample_generator_mdp.prepare_mdp(
            submdp.model,
            submdp.quotient_state_map,
            simple_holes_bit_vector,
        )
        conflict = self.counterexample_generator_mdp.construct_conflict(
            index,
            prop.threshold,
            simple_holes_bit_vector,
            None,
            family.mdp.quotient_state_map,
        )
        conflicts.append(conflict)

        return conflicts, accepting_assignment
