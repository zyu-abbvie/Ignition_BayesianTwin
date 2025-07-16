# test_optimizer.py

import json
from core.optimizer import BayesianOptimizer

# Sample input configuration
# sample_config = {
#     "parameters": [
#         {"name": "flowrate", "parameter_type": "range", "value_type":"float", "lb": 0.1, "ub": 1.0},
#         {"name": "temperature", "parameter_type": "range", "value_type":"float", "lb": 25, "ub": 80}
#     ],
#     "objective_name": "yields"
# }

sample_config = {
    "parameters": [
        {"name": "screw_speed", "parameter_type": "range", "value_type": "float", "lb": 100, "ub": 600},           # RPM
        {"name": "feed_rate", "parameter_type": "range", "value_type": "float", "lb": 5, "ub": 25},               # g/min
        {"name": "liquid_ratio", "parameter_type": "range", "value_type": "float", "lb": 0.05, "ub": 0.3},        # w/w
        {"name": "barrel_temperature", "parameter_type": "range", "value_type": "float", "lb": 20, "ub": 80},     # °C
        {"name": "binder_concentration", "parameter_type": "range", "value_type": "float", "lb": 0.01, "ub": 0.15}# w/w
    ],
    "objective_name": "granule_quality_index"  # or "yield", "PSD_target_match", depending on your use case
}

# Optional: define a simple status callback to print status updates
def status_callback(msg):
    print(f"[STATUS CALLBACK] {msg}")

# Instantiate the optimizer

optimizer = BayesianOptimizer(sample_config, status_callback=status_callback)
print("[TEST] BayesianOptimizer loaded successfully.")

# Optional: try a suggestion
trial_index, suggestion = optimizer.suggest_next()
print(f"[TEST] Suggestion (trial #{trial_index}): {suggestion}")

