import pandas as pd
import json
import numpy as np

def parse_config(payload):
    return json.loads(payload)

def parse_input_parameters(payload):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse input JSON: {e}")
    elif not isinstance(payload, dict):
        raise TypeError("Input payload must be a dict or JSON string.")

    if "parameters" in payload:
        return payload["parameters"]
    else:
        return payload  # assume it's already the parameters dict

def parse_result_data(payload):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse result JSON: {e}")
    elif not isinstance(payload, dict):
        raise TypeError("Result payload must be a dict or JSON string.")

    return payload.get("parameters", {}), payload.get("metrics", {})

def load_default_config():
    config = {
    "parameters": [
        {"name": "screw_speed", "parameter_type": "range", "value_type": "float", "lb": 100, "ub": 600},           # RPM
        {"name": "feed_rate", "parameter_type": "range", "value_type": "float", "lb": 5, "ub": 25},               # g/min
        {"name": "liquid_ratio", "parameter_type": "range", "value_type": "float", "lb": 0.05, "ub": 0.3},        # w/w
        {"name": "barrel_temperature", "parameter_type": "range", "value_type": "float", "lb": 20, "ub": 80},     # °C
        {"name": "binder_concentration", "parameter_type": "range", "value_type": "float", "lb": 0.01, "ub": 0.15}# w/w
    ],
    "objective_name": "granule_quality_index"  # or "yield", "PSD_target_match", depending on your use case
}

# {
#         "experiment_name": "mqtt_bayes_exp",
#         "parameters": [
#             {
#                 "name": "x1",
#                 "type": "range",
#                 "parameter_type": "float",  # ✅ string, not Python type
#                 "bounds": [0.0, 1.0]
#             },
#             {
#                 "name": "x2",
#                 "type": "range",
#                 "parameter_type": "float",
#                 "bounds": [0.0, 1.0]
#             }
#         ],
#         "objective_name": "outcome",
#         "minimize": False,
#         "outcome_constraints": [],
#         "description": "Test exp",
#         "owner": "zhenzi"
#     }

    return config

def detect_trial_changes(new_trial: dict, df: pd.DataFrame, metric_name: str):
    df_new = pd.json_normalize(new_trial)
    df_new.rename(columns=lambda x: x.split('.')[-1], inplace=True)

    df_compare = df[df_new.columns]  # ensure matching columns

    for i in df_new.index:
        row_changes = {}
        for col in df_new.columns:
            old = df_compare.loc[i, col]
            new = df_new.loc[i, col]

            try:
                old_f = round(float(old), 2)
                new_f = round(float(new), 2)
                if pd.isna(old_f) != pd.isna(new_f) or not np.isclose(old_f, new_f, atol=0.01, equal_nan=True):
                    row_changes[col] = {"old": old_f, "new": new_f}
            except:
                if str(old) != str(new):
                    row_changes[col] = {"old": str(old), "new": str(new)}

        if row_changes:
            trial_idx = df_new.loc[i, "trial_index"]
            return trial_idx, row_changes

    return None, {}




# def detect_trial_changes(new_trial: dict, df: pd.DataFrame, metric_name: str):
#     """
#     Compare new_trial against optimizer state in df.
#     Returns: (matched_index, change_dict) — only one change assumed.
#     """
#     params = new_trial[0].get("parameters", {})
#     metrics = new_trial[0].get("metrics", {})

#     matched_idx = None
#     for i, row in df.iterrows():
#         try:
#             match = all(round(float(row[k]), 2) == round(float(v), 2) for k, v in params.items() if k in row)
#         except Exception:
#             continue
#         if match:
#             matched_idx = i
#             break

#     change = {}
#     if matched_idx is not None:
#         row = df.iloc[matched_idx]

#         for k, v in params.items():
#             if k in row and round(float(row[k]), 2) != round(float(v), 2):
#                 return matched_idx, {k: {"old": float(row[k]), "new": float(v)}}

#         if metric_name in metrics and metric_name in df.columns:
#             try:
#                 new_metric = float(metrics[metric_name])
#                 old_metric = row[metric_name]
#                 if pd.isna(old_metric) or not np.isclose(float(old_metric), new_metric, atol=1e-5):
#                     return matched_idx, {metric_name: {"old": old_metric, "new": new_metric}}
#             except Exception:
#                 return matched_idx, {metric_name: {"old": row[metric_name], "new": metrics[metric_name]}}

#     return matched_idx, change