#!/bin/bash
declare -a models=("drone-4-1" "drone-4-2"
                   "drone-8-2" "grid-avoid-4-0" "grid-avoid-4-0.1"
                   "grid-large-20-5" "grid-large-30-5" "lanes-100-combined-new"
                   "maze-alex" "network-3-8-20" "network-prio-2-8-20"
                   "refuel-06" "refuel-08" "refuel-20" "rocks-12" "rocks-16")

for model in ${models[@]}; do
    python3 paynt.py --project models/pomdp/storm-integration/${model} --method cegis --ce-generator=mdp --benchmarking="classic" --timeout=600
done

for model in ${models[@]}; do
    python3 paynt.py --project models/pomdp/storm-integration/${model} --method cegis --ce-generator=mdp-randomised --benchmarking="classic" --timeout=600
done

for model in ${models[@]}; do
    python3 paynt.py --project models/pomdp/storm-integration/${model} --method cegis --ce-generator=mdp-simple-holes-stats --benchmarking="classic" --timeout=600
done

for model in ${models[@]}; do
    python3 paynt.py --project models/pomdp/storm-integration/${model} --method cegis --ce-generator=mdp-simple-holes-stats --benchmarking="classic" --simple-holes-stats-file benchmarking/simple_holes_in_conflict/models_pomdp_storm-integration_${model} --timeout=600
done


