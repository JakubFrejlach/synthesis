# import switss stuff if installed
import importlib

import stormpy

from .storm import ConflictGeneratorStorm

if importlib.util.find_spec("switss") is not None:
    from switss.model import ReachabilityForm
    from switss.model import MDP as SWITSS_MDP
    from switss.model import DTMC as SWITSS_DTMC
    from switss.problem.qsheur import QSHeur

import logging

from opcode import hasconst
from scipy.sparse import dok_matrix

from paynt.quotient.property import OptimalityProperty

logger = logging.getLogger(__name__)


class ConflictGeneratorSwitss(ConflictGeneratorStorm):
    def __init__(self, quotient, mdp_ce=True):
        self.mdp_ce = mdp_ce
        super().__init__(quotient)

    @property
    def name(self):
        return f"(SWITSS - {'MDP' if self.mdp_ce else 'DTMC'})"

    def initialize(self):
        self.counterexample_generator = QSHeur(solver="cbc", iterations=10)

    def construct_conflict_mdp(
        self, family, assignment, dtmc, conflict_requests, accepting_assignment
    ):
        subfamily = family.copy()
        simple_holes = [
            hole_index
            for hole_index in subfamily.hole_indices
            if family.mdp.hole_simple[hole_index]
        ]
        non_simple_holes = {
            hole_index
            for hole_index in subfamily.hole_indices
            if not family.mdp.hole_simple[hole_index]
        }
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

        if prop.minimizing:
            # safety
            threshold = prop.threshold
            subformula = prop.property.raw_formula.subformula.subformula
            if isinstance(subformula, stormpy.logic.AtomicLabelFormula):
                target_label = subformula.label
            else:
                assert isinstance(subformula, stormpy.logic.AtomicExpressionFormula)
                target_label = str(subformula)
        else:
            # liveness: flip threshold
            threshold = 1 - prop.threshold
            target_label = "target"

        # construct a labeled SWITSS DTMC
        switss_mdp = SWITSS_MDP.from_stormpy(submdp.model)
        for i, state in enumerate(submdp.model.states):
            # copy labels
            for label in state.labels:
                switss_mdp.add_label(i, label)

        # label states by relevant holes id

        for submdp_state in range(submdp.states):
            mdp_state = submdp.quotient_state_map[submdp_state]
            for hole in submdp.quotient_container.coloring.state_to_holes[mdp_state]:
                switss_mdp.add_label(submdp_state, str(hole))

        if prop.minimizing:
            switss_mdp_rf, _, _ = ReachabilityForm.reduce(
                switss_mdp, "init", target_label
            )
            results = list(
                self.counterexample_generator.solveiter(
                    switss_mdp_rf, threshold, "max", ignore_consistency_checks=True
                )
            )
            witnessing_subsystem = results[-1].subsystem.subsys.system
            # FIXME: implement unreachable states removal in MDP in SWITSS
            # witnessing_subsystem = SWITSS_DTMC.remove_unreachable_states(
            #     witnessing_subsystem, init_label="init"
            # )

            conflict = set(
                [
                    int(label)
                    for label in witnessing_subsystem.states_by_label.keys()
                    if label.isnumeric()
                ]
            )
            conflict = list(conflict)
        else:
            no_states = switss_mdp.N
            # compute all bottom SCCs
            (
                scc_arr,
                proper_scc_mask,
                no_of_sccs,
            ) = switss_mdp.maximal_end_components()

            total_actions = 0
            total_actions += len([i for i in proper_scc_mask if i])
            for state in range(no_states):
                i_scc = scc_arr[state]
                if proper_scc_mask[i_scc] != 1:
                    total_actions += len(switss_mdp.actions_by_state[state])

            new_transation_matrix = dok_matrix((total_actions, no_of_sccs))

            labels = {"init": {scc_arr[0]}, "target": set()}

            i = 0
            new_index_by_state_action = {}
            for state, action in switss_mdp.index_by_state_action:
                state_scc = scc_arr[state]

                labels[str(state)] = set()
                # save old id of state via label
                labels[str(state)].add(state_scc)

                if proper_scc_mask[state_scc] == 1:
                    if not any(
                        [
                            True
                            for key in new_index_by_state_action
                            if key[0] == state_scc
                        ]
                    ):
                        labels["target"].add(state_scc)
                        new_transation_matrix[i, state_scc] = 1
                        new_index_by_state_action[(state_scc, action)] = i
                        i += 1
                else:
                    for j in range(no_states):
                        j_scc = scc_arr[j]
                        new_transation_matrix[i, j_scc] += switss_mdp.P[i, j]
                    new_index_by_state_action[(state_scc, action)] = i
                    i += 1

            transformed_switss_mdp = SWITSS_MDP(
                new_transation_matrix,
                new_index_by_state_action,
                label_to_states=labels,
            )
            switss_mdp_rf, _, _ = ReachabilityForm.reduce(
                transformed_switss_mdp, "init", target_label
            )
            results = list(
                self.counterexample_generator.solveiter(
                    switss_mdp_rf, threshold, "max", ignore_consistency_checks=True
                )
            )
            witnessing_subsystem = results[-1].subsystem.subsys.system
            # FIXME: implement unreachable states removal in MDP in SWITSS
            # witnessing_subsystem = SWITSS_DTMC.remove_unreachable_states(
            #     witnessing_subsystem, init_label="init"
            # )

            conflict = set()
            for state_label in witnessing_subsystem.states_by_label.keys():
                if state_label.isnumeric():
                    conflict |= switss_mdp.labels_by_state[int(state_label)]
            conflict = [int(hole_id) for hole_id in conflict if hole_id.isnumeric()]
        return conflict

    def construct_conflict_dtmc(self, dtmc, prop):
        if prop.minimizing:
            # safety
            threshold = prop.threshold
            subformula = prop.property.raw_formula.subformula.subformula
            if isinstance(subformula, stormpy.logic.AtomicLabelFormula):
                target_label = subformula.label
            else:
                assert isinstance(subformula, stormpy.logic.AtomicExpressionFormula)
                target_label = str(subformula)
        else:
            # liveness: flip threshold
            threshold = 1 - prop.threshold
            target_label = "target"

        # construct a labeled SWITSS DTMC
        switss_dtmc = SWITSS_DTMC.from_stormpy(dtmc.model)
        for i, state in enumerate(dtmc.model.states):
            # copy labels
            for label in state.labels:
                switss_dtmc.add_label(i, label)

        # label states by relevant holes id
        for dtmc_state in range(dtmc.states):
            mdp_state = dtmc.quotient_state_map[dtmc_state]
            for hole in dtmc.quotient_container.coloring.state_to_holes[mdp_state]:
                switss_dtmc.add_label(dtmc_state, str(hole))

        if prop.minimizing:
            switss_dtmc_rf, _, _ = ReachabilityForm.reduce(
                switss_dtmc, "init", target_label
            )
            results = list(
                self.counterexample_generator.solveiter(
                    switss_dtmc_rf, threshold, "max", ignore_consistency_checks=True
                )
            )
            witnessing_subsystem = results[-1].subsystem.subsys.system
            witnessing_subsystem = SWITSS_DTMC.remove_unreachable_states(
                witnessing_subsystem, init_label="init"
            )

            conflict = set(
                [
                    int(label)
                    for label in witnessing_subsystem.states_by_label.keys()
                    if label.isnumeric()
                ]
            )
            conflict = list(conflict)
        else:
            no_states = switss_dtmc.N

            # compute all bottom SCCs
            (
                scc_arr,
                proper_scc_mask,
                no_of_sccs,
            ) = switss_dtmc.maximal_end_components()
            new_transation_matrix = dok_matrix((no_of_sccs, no_of_sccs))

            labels = {"init": {scc_arr[0]}, "target": set()}

            # collapse states according to computed bottom SCCs
            for i in range(no_states):
                i_scc = scc_arr[i]

                labels[str(i)] = set()
                # save old id of state via label
                labels[str(i)].add(i_scc)

                if proper_scc_mask[i_scc] == 1:
                    # label target states
                    labels["target"].add(i_scc)
                    new_transation_matrix[i_scc, i_scc] = 1
                else:
                    for j in range(no_states):
                        j_scc = scc_arr[j]
                        new_transation_matrix[i_scc, j_scc] += switss_dtmc.P[i, j]

            transformed_switss_dtmc = SWITSS_DTMC(
                new_transation_matrix, label_to_states=labels
            )
            switss_dtmc_rf, _, _ = ReachabilityForm.reduce(
                transformed_switss_dtmc, "init", target_label
            )
            results = list(
                self.counterexample_generator.solveiter(
                    switss_dtmc_rf, threshold, "max", ignore_consistency_checks=True
                )
            )
            witnessing_subsystem = results[-1].subsystem.subsys.system
            witnessing_subsystem = SWITSS_DTMC.remove_unreachable_states(
                witnessing_subsystem, init_label="init"
            )

            conflict = set()
            for state_label in witnessing_subsystem.states_by_label.keys():
                if state_label.isnumeric():
                    conflict |= switss_dtmc.labels_by_state[int(state_label)]
            conflict = [int(hole_id) for hole_id in conflict if hole_id.isnumeric()]

        return conflict

    def construct_conflicts(
        self, family, assignment, dtmc, conflict_requests, accepting_assignment
    ):

        if self.mdp_ce:
            assert (
                len(conflict_requests) == 1
            ), "we don't know how to handle multiple conflict requests in this mode, consider CEGIS in another mode"

        for request in conflict_requests:
            assert not request[
                1
            ].reward, "we don't know how to handle reward properties in this mode, conside CEGIS in another mode"

        # # generalize simple holes, i.e. starting from the full family, fix each
        # # non-simple hole to the option selected by the assignment
        # subfamily = family.copy()
        # simple_holes = [
        #     hole_index
        #     for hole_index in subfamily.hole_indices
        #     if family.mdp.hole_simple[hole_index]
        # ]
        # non_simple_holes = [
        #     hole_index
        #     for hole_index in subfamily.hole_indices
        #     if not family.mdp.hole_simple[hole_index]
        # ]
        # for hole_index in non_simple_holes:
        #     subfamily.assume_hole_options(hole_index, assignment[hole_index].options)
        # self.quotient.build(subfamily)
        # submdp = subfamily.mdp

        # index, prop, _, family_result = conflict_requests[0]

        # # check primary direction
        # primary = submdp.model_check_property(prop)
        # if primary.sat:
        #     # found satisfying assignment
        #     selection, _, _, _, consistent = self.quotient.scheduler_consistent(
        #         submdp, prop, primary.result
        #     )
        #     assert consistent
        #     if isinstance(prop, OptimalityProperty):
        #         self.quotient.specification.optimality.update_optimum(primary.value)
        #     accepting_assignment = family.copy()
        #     for hole_index in family.hole_indices:
        #         accepting_assignment.assume_hole_options(
        #             hole_index, selection[hole_index]
        #         )

        conflicts = []
        for request in conflict_requests:
            index, prop, member_result, family_result = request

            if self.mdp_ce:
                conflict = self.construct_conflict_mdp(
                    family, assignment, dtmc, conflict_requests, accepting_assignment
                )
            else:
                conflict = self.construct_conflict_dtmc(dtmc, prop)

            conflicts.append(conflict)

        return conflicts, accepting_assignment
