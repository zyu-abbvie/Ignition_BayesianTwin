from ax.api.client import Client
from ax.api.configs import RangeParameterConfig, ChoiceParameterConfig
import json 
import pandas as pd

class BayesianOptimizer:
    def __init__(self, config, status_callback=None):
        self.status_callback = status_callback
        self.client = Client()
        self.config = config
        self.trial_indices = {}
        self._configure_experiment()

    def _configure_experiment(self):
        param_configs = []

        for p in self.config["parameters"]:
            if p["parameter_type"] == "range":
                param_configs.append(RangeParameterConfig(
                    name=p["name"],
                    parameter_type=p["value_type"],
                    bounds=tuple((p["lb"],p["ub"]))
                ))
            elif p["parameter_type"] == "choice":
                param_configs.append(ChoiceParameterConfig(
                    name=p["name"],
                    parameter_type=p["value_type"],
                    values=p["values"]
                ))
            else:
                raise ValueError(f"Unsupported parameter type: {p['parameter_type']}")

        self.client.configure_experiment(
            parameters=param_configs,
            name=self.config.get("experiment_name", "default_exp"),
            description=self.config.get("description", ""),
            owner=self.config.get("owner", "platform")
        )

        self.client.configure_optimization(
            objective=self.config["objective_name"],
            outcome_constraints=self.config.get("outcome_constraints", [])
        )

    def suggest_next(self):
        trials = self.client.get_next_trials(max_trials=1)
        trial_index = list(trials.keys())[0]
        parameters = trials[trial_index]
        self.trial_indices[trial_index] = parameters
        return trial_index, parameters

    def complete_or_attach_trial(self, parameters, data):
        # Standardize parameters: convert to float and round to 2 decimals
        def normalize_param_dict(d):
            result = {}
            for k, v in d.items():
                try:
                    result[k] = round(float(v), 2)
                except Exception as e:
                    raise ValueError(f"Invalid parameter value for '{k}': {v} ({e})")
            return result

        # Normalize both input parameters and existing ones for comparison
        norm_input_params = normalize_param_dict(parameters)

        matched_index = None
        for idx, trial_params in self.trial_indices.items():
            norm_trial_params = normalize_param_dict(trial_params)
            if norm_input_params == norm_trial_params:
                matched_index = idx
                break

        # Format metrics to float or (float, float)
        cleaned_data = {}
        for k, v in data.items():
            try:
                if isinstance(v, (list, tuple)) and len(v) == 2:
                    cleaned_data[k] = (float(v[0]), float(v[1]))
                else:
                    cleaned_data[k] = float(v) if v is not None else None
            except Exception as e:
                raise ValueError(f"Invalid metric format for '{k}': {v} ({e})")

        if matched_index is not None:
            self.client.complete_trial(trial_index=matched_index, raw_data=cleaned_data)
            return matched_index
        else:
            idx = self.client.attach_trial(parameters=norm_input_params)
            self.client.complete_trial(trial_index=idx, raw_data=cleaned_data)
            return idx

    def get_best_parameters(self):
        
        return self.client.get_best_parameterization()
    
    
    def custom_summarize(self) -> pd.DataFrame:
        from ax.analysis.summary import Summary
        (card,) = Summary(omit_empty_columns=False).compute(
            experiment=self.client._experiment,
            generation_strategy=self.client._generation_strategy,
        )

        return card.df