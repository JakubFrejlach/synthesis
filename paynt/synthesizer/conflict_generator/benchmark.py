import logging
import random
from collections import defaultdict

import stormpy.synthesis
from paynt.quotient.property import OptimalityProperty
from paynt.utils.profiler import Timer

logger = logging.getLogger(__name__)
from .switss import ConflictGeneratorSwitss


class ConflictGeneratorBenchmark:
    def __init__(self, quotient):
        self.quotient = quotient
        self.counterexample_generator = None

    @property
    def name(self):
        return "(Benchmark)"

    def initialize(self):
        quotient_relevant_holes = self.quotient.coloring.state_to_holes
        self.formulae = self.quotient.specification.stormpy_formulae()
        self.counterexample_generator = stormpy.synthesis.CounterexampleGenerator(
            self.quotient.quotient_mdp,
            self.quotient.design_space.num_holes,
            quotient_relevant_holes,
            self.formulae,
        )
        # MDP CE generator for benchmarking
        self.counterexample_generator_mdp = (
            stormpy.synthesis.CounterexampleGeneratorMdp(
                self.quotient.quotient_mdp,
                self.quotient.design_space.num_holes,
                quotient_relevant_holes,
                self.formulae,
            )
        )
        # SWITSS CE generator for benchmarking
        # self.conflict_generator_switss = ConflictGeneratorSwitss(self.quotient)
        # self.conflict_generator_switss.initialize()

        self.mdp_conflicts = []
        self.dtmc_conflicts = []
        # self.switss_conflicts = []
        self.mdp_timer = Timer()
        self.dtmc_timer = Timer()
        # self.switss_timer = Timer()

    #     self.simple_holes_stats = defaultdict(lambda: 0, simple_holes_stats)
    #     self.simple_holes_stats_avg = None

    # def simple_holes_stats_avg_compute(self, simple_holes_count):
    #     self.simple_holes_stats_avg = (
    #         sum(self.simple_holes_stats.values()) / simple_holes_count
    #         if self.simple_holes_stats
    #         else 0
    #     )

    def print_conflict_stats(self):
        print(f"MDP conflicts{self.mdp_conflicts}")
        print(f"MDP time{self.mdp_timer.time}")
        print(f"DTMC conflicts{self.dtmc_conflicts}")
        print(f"DTMC time{self.dtmc_timer.time}")
        # print(f"SWITSS conflicts{self.switss_conflicts}")
        # print(f"SWITSS time{self.switss_timer.time}")

    def get_conflict_stats(self):
        return {
            "mdp_avg_conflict_size": round(
                sum(self.mdp_conflicts) / len(self.mdp_conflicts), 3
            )
            if self.mdp_conflicts
            else None,
            "dtmc_avg_conflict_size": round(
                sum(self.dtmc_conflicts) / len(self.dtmc_conflicts), 3
            )
            if self.dtmc_conflicts
            else None,
            # "switss_avg_conflict_size": round(
            #     sum(self.switss_conflicts) / len(self.switss_conflicts), 3
            # )
            # if self.switss_conflicts
            # else None,
            "mdp_total_time": round(self.mdp_timer.time, 3),
            "dtmc_total_time": round(self.dtmc_timer.time, 3),
            # "switss_total_time": round(self.switss_timer.time, 3),
            "mdp_avg_time_per_conflict": round(
                self.mdp_timer.time / len(self.mdp_conflicts), 3
            )
            if self.mdp_conflicts
            else None,
            "dtmc_avg_time_per_conflict": round(
                self.dtmc_timer.time / len(self.dtmc_conflicts), 3
            )
            if self.dtmc_conflicts
            else None,
            # "switss_avg_time_per_conflict": round(
            #     self.switss_timer.time / len(self.switss_conflicts), 3
            # )
            # if self.switss_conflicts
            # else None,
        }

    def construct_conflicts(
        self, family, assignment, dtmc, conflict_requests, accepting_assignment
    ):

        self.dtmc_timer.start()
        self.counterexample_generator.prepare_dtmc(dtmc.model, dtmc.quotient_state_map)

        # DTMC conflict
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
        self.dtmc_timer.stop()
        self.dtmc_conflicts.append(len(conflicts[0]))

        # MDP conflict
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

        # assumed_simple_holes = [hole for hole in simple_holes if random.randint(0, 1)]
        assumed_simple_holes = []

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

        self.mdp_timer.start()
        self.counterexample_generator_mdp.prepare_mdp(
            submdp.model,
            submdp.quotient_state_map,
            simple_holes_bit_vector,
            [hole.options[0] for hole in assignment],
        )
        mdp_conflict = self.counterexample_generator_mdp.construct_conflict(
            index,
            prop.threshold,
            # simple_holes_bit_vector,
            None,
            family.mdp.quotient_state_map,
        )
        self.mdp_timer.stop()
        self.mdp_conflicts.append(len(mdp_conflict))
        # print(f"DTMC - Len: {len(conflict)}, {conflict}")
        # print(f"MDP - Len: {len(mdp_conflict)}, {mdp_conflict}")

        # print(
        #     f"non simple holes in conflict MDP: Len: {len(set(non_simple_holes).intersection(set(mdp_conflict)))} {set(non_simple_holes).intersection(set(mdp_conflict))}"
        # )

        # SWITSS conflict
        # if not self.formulae[index].is_reward_operator:
        #     self.switss_timer.start()
        #     (switss_conflict, _,) = self.conflict_generator_switss.construct_conflicts(
        #         family, assignment, dtmc, conflict_requests, accepting_assignment
        #     )
        #     self.switss_timer.stop()
        #     self.switss_conflicts.append(len(switss_conflict[0]))
        # elif self.switss_conflicts is not None:
        #     self.switss_conflicts = None

        return conflicts, accepting_assignment
