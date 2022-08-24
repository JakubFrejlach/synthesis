import stormpy

from .prism_parser import PrismParser
from .jani import JaniUnfolder
from .pomdp_parser import PomdpParser
from ..synthesizers.quotient import *
from ..synthesizers.quotient_pomdp import POMDPQuotientContainer

from ..synthesizers.models import MarkovChain
from ..profiler import Profiler 

import logging
logger = logging.getLogger(__name__)


class Sketch:
    '''
    Basic container for a sketch: a program, a specification and a quotient
    container.'''

    # if True, the sketch is assumed to be a hole-free MDP
    hyperproperty_synthesis = False

    @classmethod
    def substitute_suffix(cls, string, delimiter, suffix):
        '''Subsitute the suffix behind the last delimiter with the suffix.'''
        output_string = string.split(delimiter)
        output_string[-1] = str(suffix)
        output_string = delimiter.join(output_string)
        return output_string

    def __init__(self, sketch_path, filetype, export,
        properties_path, constant_str):

        Profiler.initialize()
        Profiler.start("sketch")

        # TODO
        self.sketch_path = sketch_path
        self.filetype = filetype
        self.properties_path = properties_path
        self.constant_str = constant_str
        
        # design space; might be initialized by the quotient
        self.design_space = None
        # the specification
        self.specification = None
        # quotient model explicitly
        self.explicit_quotient = None
        # quotient container
        self.quotient = None

        # PRISM program
        self.prism = None
        # for each hole, a list of parsed PRISM expressions used for subsitutions
        self.hole_expressions = None        
        # (dtmc sketch) jani unfolder
        self.jani_unfolder = None

        # load the sketch
        logger.info(f"Loading sketch from {sketch_path}...")
        if filetype == "prism":
            self.read_prism(sketch_path, constant_str, properties_path)
        elif filetype == "drn":
            self.explicit_quotient = PomdpParser.read_pomdp_drn(sketch_path)
            spec = PrismParser.parse_specification(properties_path)
            self.update_specification(spec)
        elif filetype == "pomdp":
            self.explicit_quotient = PomdpParser.read_pomdp_solve(sketch_path)
            spec = PrismParser.parse_specification(properties_path)
            self.update_specification(spec)
        else:
            raise TypeError("unknown input filetype")
                    
        logger.info(f"Found the following specification: {self.specification}")


        logger.info(f"Initializing the quotient ...")
        if self.is_dtmc:
            self.quotient = DTMCQuotientContainer(self, self.jani_unfolder.action_to_hole_options)
        elif self.is_ma:
            self.quotient = MAQuotientContainer(self)
        elif self.is_mdp:
            assert Sketch.hyperproperty_synthesis, "must use --hyperproperty option with MDP input files"
            self.quotient = HyperPropertyQuotientContainer(self)
        elif self.is_pomdp:
            self.quotient = POMDPQuotientContainer(self)
        else:
            raise TypeError("unknown sketch type")

        if export is not None:
            if export == "jani":
                assert self.jani_unfolder is not None, "Jani unfolder was not used"
                self.jani_unfolder.write_jani(sketch_path)
            if export == "drn":
                output_path = Sketch.substitute_suffix(sketch_path, '.', 'drn')
                stormpy.export_to_drn(self.explicit_quotient, output_path)
            if export == "pomdp":
                assert self.is_pomdp, "cannot --export pomdp with non-POMDP sketches"
                PomdpParser.write_model_in_pomdp_solve_format(sketch_path, self.quotient)
            exit()
        
        logger.info(f"Sketch parsing complete.")
        logger.info(f"Sketch has {self.design_space.num_holes} holes")
        logger.info(f"Design space size: {self.design_space.size}")
        Profiler.stop()

    
    def read_prism(self, sketch_path, constant_str, properties_path):

        prism, self.hole_expressions, self.design_space, constant_map = PrismParser.read_prism_sketch(sketch_path, constant_str)
        specification = PrismParser.parse_specification(properties_path, prism, constant_map)

        # if PRISM describes a DTMC, unfold hole options in jani
        if prism.model_type == stormpy.storage.PrismModelType.DTMC:
            # unfold hole options in Jani
            self.jani_unfolder = JaniUnfolder(prism, self.hole_expressions, specification, self.design_space)
            specification = self.jani_unfolder.specification
            quotient_mdp = self.jani_unfolder.quotient_mdp

        # specification is now finalized and will be used during the
        # construction of Markov chains
        self.prism = prism
        self.update_specification(specification)

        # construct the quotient if one has not been constructed yet
        if prism.model_type != stormpy.storage.PrismModelType.DTMC:
            quotient_mdp = MarkovChain.from_prism(self.prism)

        # success
        self.explicit_quotient = quotient_mdp
        logger.debug("Constructed quotient MDP having {} states and {} actions.".format(
            quotient_mdp.nr_states, quotient_mdp.nr_choices))

    def is_prism_and_of_type(self, of_type):
        return self.prism is not None and self.prism.model_type == of_type

    def set_design_space(self, design_space):
        self.design_space = design_space
        self.design_space.property_indices = self.specification.all_constraint_indices()

    def update_specification(self, specification):
        self.specification = specification
        MarkovChain.initialize(self.specification.stormpy_formulae())
        

    @property
    def is_dtmc(self):
        return self.is_prism_and_of_type(stormpy.storage.PrismModelType.DTMC)
    
    @property
    def is_ctmc(self):
        return self.is_prism_and_of_type(stormpy.storage.PrismModelType.CTMC)

    @property
    def is_ma(self):
        return self.is_prism_and_of_type(stormpy.storage.PrismModelType.MA)

    @property
    def is_mdp(self):
        return self.is_prism_and_of_type(stormpy.storage.PrismModelType.MDP)

    @property
    def is_pomdp(self):
        return self.explicit_quotient.is_nondeterministic_model and self.explicit_quotient.is_partially_observable

    def restrict_prism(self, assignment):
        assert assignment.size == 1
        substitution = {}
        for hole_index,hole in enumerate(assignment):
            ev = self.prism.get_constant(hole.name).expression_variable
            expr = self.hole_expressions[hole_index][hole.options[0]]
            substitution[ev] = expr
        program = self.prism.define_constants(substitution)
        model = stormpy.build_sparse_model_with_options(program, MarkovChain.builder_options)
        return model
