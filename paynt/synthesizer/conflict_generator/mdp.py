import logging
import random
from collections import defaultdict

import stormpy
from paynt.quotient.property import OptimalityProperty

from .storm import ConflictGeneratorStorm

logger = logging.getLogger(__name__)


class ConflictGeneratorMdp(ConflictGeneratorStorm):
    @property
    def name(self):
        return f"(MDP generalization{self.variant_label})"

    @property
    def variant_label(self):
        return f" - {self.variant}" if self.variant is not None else ""

    def __init__(self, *args, simple_holes_stats=None, variant=None, **kwargs):
        self.simple_holes_stats = defaultdict(
            lambda: 0, {} if simple_holes_stats is None else simple_holes_stats
        )
        self.simple_holes_stats_avg = None
        self.variant = variant
        super().__init__(*args, **kwargs)

    def initialize(self):
        quotient_relevant_holes = self.quotient.coloring.state_to_holes
        formulae = self.quotient.specification.stormpy_formulae()
        self.counterexample_generator = stormpy.synthesis.CounterexampleGeneratorMdp(
            self.quotient.quotient_mdp,
            self.quotient.design_space.num_holes,
            quotient_relevant_holes,
            formulae,
        )

    def simple_holes_stats_avg_compute(self, simple_holes_count):
        self.simple_holes_stats_avg = (
            sum(self.simple_holes_stats.values()) / simple_holes_count
            if self.simple_holes_stats
            else 0
        )

    def construct_conflicts(
        self, family, assignment, dtmc, conflict_requests, accepting_assignment
    ):

        assert (
            len(conflict_requests) == 1
        ), "we don't know how to handle multiple conflict requests in this mode, consider CEGIS in another mode"

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

        # Compute average of simple holes occurence for generalization baseline
        # if simple hole stats variant is enabled
        if self.simple_holes_stats_avg is None and self.variant == "simple-holes-stats":
            self.simple_holes_stats_avg_compute(len(simple_holes))

        # Based on the variant decide which additional simple holes should be
        # fixed by the assignment
        if self.variant == "randomised":
            assumed_simple_holes = [
                hole for hole in simple_holes if random.randint(0, 1)
            ]
        elif self.variant == "simple-holes-stats":
            assumed_simple_holes = [
                hole
                for hole in simple_holes
                if self.simple_holes_stats[hole] < self.simple_holes_stats_avg
            ]
        else:
            assumed_simple_holes = []

        # generalize simple holes, i.e. starting from the full family, fix each
        # non-simple hole to the option selected by the assignment
        for hole_index in non_simple_holes + assumed_simple_holes:
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
            len(non_simple_holes) + len(simple_holes),
            list(set(simple_holes) - set(assumed_simple_holes)),
        )

        # Prepare the MDP for the state exploration and conflict construction
        self.counterexample_generator.prepare_mdp(
            submdp.model,
            submdp.quotient_state_map,
            simple_holes_bit_vector,
            [hole.options[0] for hole in assignment],
            True if self.variant == "holes-positions" else False,
        )

        # Get conflicts
        conflict = self.counterexample_generator.construct_conflict(
            index,
            prop.threshold,
            None,
            family.mdp.quotient_state_map,
        )
        conflicts = [conflict]

        return conflicts, accepting_assignment
