"""
Verification of Convergence Simulator (Gate A10) across multiple deterministic seeds.
Inspects distance reduction and cosine similarity series across rounds.
"""

from training.sim.convergence_sim import WitnessConvergenceSimulator


def verify_convergence():
    sim = WitnessConvergenceSimulator(learning_rate=0.45)
    seeds = [42, 101, 2024, 777]

    print("\n" + "=" * 70)
    print("GATE A10 CONVERGENCE SIMULATION MULTI-SEED AUDIT")
    print("=" * 70)

    all_passed = True
    for s in seeds:
        rep = sim.run_simulation(num_rounds=6, seed=s)
        print(f"\nSeed {s}:")
        print(f"  Status: {rep['status']}")
        print(f"  Initial Distance: {rep['initial_distance']:.4f} -> Final Distance: {rep['final_distance']:.4f}")
        print(f"  Distance Reduction: {rep['distance_reduction_pct']}%")
        print(f"  Final Cosine Similarity: {rep['final_cosine_similarity']:.4f}")
        print("  Round Progression:")
        for r in rep["round_history"]:
            print(f"    Round {r['round']}: dist={r['distance_to_target']:.4f}, cos_sim={r['cosine_similarity']:.4f}, selected_variant={r['selected_variant_index']}")

        if not rep["converged"] or rep["distance_reduction_pct"] <= 0:
            all_passed = False

    print("\n" + "=" * 70)
    print(f"Gate A10 Overall Result: {'PASS' if all_passed else 'FAIL'}")
    print("=" * 70)


if __name__ == "__main__":
    verify_convergence()
