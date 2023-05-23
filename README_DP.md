# Using Counter-Examples in Controller Synthesis for POMDPs
In this readme file we will outline everything important to be able to run PAYNT CEGIS with
the MDP counterexamples

## Installation

* Install PAYNT according to [README.md](README.md) - all the necessary prerequisites (STORM, Stormpy, carl, cvc5, pycarl, SWITSS) are already present in the project directory
* If you want to use SWITSS you need to additionally download PRISM, follow the [SWITSS README](prerequisites/switss/README.md) for the installation process

## Usage of CEGIS with MDP counterexamples
In this section we will list new options relevant for the MDP CEs usage, for the basic usage of PAYNT please refer to [README.md](README.md)

* `--ce-generator [storm|switss-mdp|switss-dtmc|mdp|mdp-randomised|mdp-holes-positions|mdp-simple-holes-stats]` - choice of CE generator and its possible variant
* `--simple-holes-stats-file FILENAME` - necessary file containing simple holes stats needed for the `mdp-simple-holes-stats` CE generator variant
* `--timeout INTEGER` - synthesis termination time in seconds

To run a set of experiments using MDP CEs, MDP CEs with randomisation, MDP CEs with simple holes stats and MDP CEs randomised with the hole position information you may run the script [benchmark.sh](benchmark.sh).


## Modified files
In this section we will describe which important files were modified/added and for what purpose

* [paynt/cli.py](paynt/cli.py) - new PAYNT command line options
* [paynt/synthesizer/conflict_generator/mdp.py](paynt/synthesizer/conflict_generator/mdp.py) - new conflict generator leveraging the MDP CEs
* [paynt/synthesizer/conflict_generator/switss.py](paynt/synthesizer/conflict_generator/switss.py) - new SWITSS CE generator
* [storm/src/storm-synthesis/synthesis/CounterexampleMdp.cpp](storm/src/storm-synthesis/synthesis/CounterexampleMdp.cpp) - new greedy counterexample generator for MDPs in STORM
* [storm/src/storm-synthesis/synthesis/CounterexampleMdp.h](storm/src/storm-synthesis/synthesis/CounterexampleMdp.h) - new greedy counterexample generator for MDPs in STORM
* [stormpy/src/synthesis/synthesis.cpp](stormpy/src/synthesis/synthesis.cpp) - necessary python bindings for the new greedy counterexample generator
