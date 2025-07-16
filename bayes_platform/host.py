
import json
import time
import threading
from core.optimizer import BayesianOptimizer
from mqtt.mqtt_handler import MQTTHandler
from utils.data_handler import parse_input_parameters, parse_result_data, detect_trial_changes
import traceback
import numpy as np 




class OptimizationHost:
    def __init__(self, address="LC/R8/133-1-1/PC06/bay"):
        
        self.TRIGGER_TOPIC   = address+"/python"
        self.SETUP_TOPIC     = address+"/setup"
        self.TAGMAP_TOPIC    = address+"/tagmap"
        self.INPUT_TOPIC     = address+"/input"
        self.RESULT_TOPIC    = address+"/result"
        self.STATUS_TOPIC    = address+"/status"
        self.PLATFORM_STATUS = address+"/platform_status"
        self.DATA_IN_TOPIC   = address+"/data_in"
        self.DATA_OUT_TOPIC  = address+"/data" 

        self.platform_running = False
        self.trigger_flag = False
        self.optimizer = None
        self.last_suggestion = {}
        self.tag_map = {}
        self.awaiting_result = False

        self.mqtt_handler = MQTTHandler(
            broker="10.94.132.35",
            port=1883,
            username="superlabuser10",
            password="123456",
            topics={
                "trigger": self.TRIGGER_TOPIC,
                "setup": self.SETUP_TOPIC,
                "tagmap": self.TAGMAP_TOPIC,
                "input": self.INPUT_TOPIC,
                "result": self.RESULT_TOPIC,
                "status": self.STATUS_TOPIC,
                "platform_status": self.PLATFORM_STATUS,
                "data_in": self.DATA_IN_TOPIC,
                "data": self.DATA_OUT_TOPIC,
            },
        )

    @property
    def config_ready(self):
        if not self.optimizer:
            print("[CONFIG CHECK] Optimizer not initialized.")
            return False
        if not self.tag_map:
            print("[CONFIG CHECK] Tag map not available.")
            return False
        for param, tag in self.tag_map.items():
            if not self.check_tag_exists(tag):
                print(f"[CONFIG CHECK] Missing or invalid tag: {tag}")
                return False
        return True

    def check_tag_exists(self, tag):
        return True if tag else False

    def handle_message(self, topic, payload):
        try:
            print(f"[MQTT] Received on {topic}: {payload}")
            if topic == self.TRIGGER_TOPIC:
                flag = json.loads(payload) if isinstance(payload, str) else payload
                self.trigger_flag = bool(flag)

                if not self.trigger_flag and self.platform_running:
                    print("[TRIGGER] Trigger turned off. Stopping optimizer immediately.")
                    self.platform_running = False
                    self.awaiting_result = False  # Cancel any in-progress result wait
                    self.mqtt_handler.publish("status", {"status": "waiting_trigger"})

                elif self.trigger_flag and not self.platform_running and self.config_ready:
                    print("[TRIGGER] Trigger turned on. Starting optimizer.")
                    self.platform_running = True
                    self.mqtt_handler.publish("status", {"status": "running"})
                    self.send_suggestion()

            elif topic == self.SETUP_TOPIC:
                config = json.loads(payload) if isinstance(payload, str) else payload
                if "parameters" not in config:
                    raise ValueError("Missing 'parameters'")
                self.optimizer = BayesianOptimizer(config, status_callback=self._optimizer_status)
                self.mqtt_handler.publish("status", {"status": "setup_config_loaded"})

            elif topic == self.TAGMAP_TOPIC:
                mapping = json.loads(payload) if isinstance(payload, str) else payload
                if not isinstance(mapping, dict):
                    self.mqtt_handler.publish("platform_status", {"Config Ready": "Contact Custom Automation Team for set up"})
                    raise ValueError("Tag map must be a dictionary")
                self.mqtt_handler.publish("status", {"status": "tagmap_loaded"})
                self.tag_map = mapping
                self.mqtt_handler.publish("status", {"status": "tagmap_loaded"})

            elif topic == self.INPUT_TOPIC:
                if not self.platform_running:
                    self.mqtt_handler.publish("status", {"status": "platform_idle", "message": "Not running"})
                    return

                payload = json.loads(payload) if isinstance(payload, str) else payload
                parameters = parse_input_parameters(payload)
                if not parameters:
                    raise ValueError("Parsed input parameters are empty.")
                self.last_suggestion = parameters
                self.awaiting_result = True
                self.mqtt_handler.publish("status", {"status": "input_received", "parameters": parameters})

            elif topic == self.RESULT_TOPIC:
                if not self.platform_running or not self.awaiting_result:
                    self.mqtt_handler.publish("status", {"status": "platform_idle", "message": "Not awaiting result"})
                    return

                payload = json.loads(payload) if isinstance(payload, str) else payload
                result_parameters, metrics = parse_result_data(payload)

                if not result_parameters or not metrics:
                    raise ValueError("Parsed result data is empty or invalid.")

                if json.dumps(result_parameters, sort_keys=True) == json.dumps(self.last_suggestion, sort_keys=True):
                    idx = self.optimizer.complete_or_attach_trial(result_parameters, metrics)
                    self.mqtt_handler.publish("status", {"status": "trial_completed", "trial_index": idx})
                    # 🔄 Publish optimizer state to data topic
                    self.publish_optimizer_state()
                else:
                    idx = self.optimizer.complete_or_attach_trial(result_parameters, metrics)
                    self.mqtt_handler.publish("status", {"status": "user_override", "trial_index": idx})
                    # 🔄 Publish optimizer state to data topic
                    self.publish_optimizer_state()

                self.awaiting_result = False
                self.send_suggestion()

            elif topic == self.DATA_IN_TOPIC:
                data = json.loads(payload) if isinstance(payload, str) else payload

                if not self.optimizer:
                    self.mqtt_handler.publish("status", {"status": "error", "message": "Optimizer not initialized."})
                    return

                trials = data.get("trials", [])
                if not trials:
                    self.mqtt_handler.publish("status", {"status": "error", "message": "No trials in input."})
                    return

                trial = trials
                metric_name = self.optimizer.config.get("objective_name", "yields")
                df = self.optimizer.custom_summarize()

                matched_idx, changes = detect_trial_changes(trial, df, metric_name)

                parameters = trial[int(matched_idx)].get("parameters", {})
                metrics = trial[int(matched_idx)].get("metrics", {})

                # If awaiting result and new input does not match expected one
                if self.awaiting_result and (
                    json.dumps(parameters, sort_keys=True) != json.dumps(self.last_suggestion, sort_keys=True)
                ):
                    self.mqtt_handler.publish("status", {
                        "status": "awaiting_result_abandoned",
                        "message": "New manual input received. Previous suggestion abandoned.",
                        "abandoned_trial": self.last_suggestion
                    })

                    self.awaiting_result = False  # Clear previous expectation

                # Complete or inject trial
                idx = self.optimizer.complete_or_attach_trial(parameters, metrics)
                action = "manual_update" if matched_idx is not None else "manual_injection"
                self.mqtt_handler.publish("status", {
                    "status": action,
                    "trial_index": idx,
                    "changes": changes
                })

                # Always trigger a fresh suggestion after user input
                self.awaiting_result = False

                self.send_suggestion()
                self.publish_optimizer_state()              


        except Exception as e:
            print("[EXCEPTION TRACEBACK]")
            traceback.print_exc()
            self.mqtt_handler.publish("status", {
                "status": "error",
                "message": str(e)
            })

    def start(self):
        self.mqtt_handler.set_message_callback(self.handle_message)
        self.mqtt_handler.connect()
        self.mqtt_handler.client.loop_start()
        self.mqtt_handler.publish("status", {"status": "idle_waiting"})
        threading.Thread(target=self.status_loop, daemon=True).start()

        try:
            while True:
                if self.config_ready and self.trigger_flag and not self.platform_running:
                    self.platform_running = True
                    self.mqtt_handler.publish("status", {"status": "running"})
                    self.send_suggestion()

                elif self.platform_running and not self.trigger_flag:
                    self.platform_running = False
                    self.mqtt_handler.publish("status", {"status": "waiting_trigger"})

                time.sleep(1)
        except KeyboardInterrupt:
            self.mqtt_handler.publish("status", {"status": "stopped"})
            self.mqtt_handler.client.loop_stop()

    def status_loop(self):
        while True:
            best_params, best_metrics, best_trial_index, best_arm_name = None, None, None, None
            model_used = False

            if self.optimizer:
                try:
                    best = self.optimizer.get_best_parameters()
                    if best:
                        best_params, best_metrics, best_trial_index, best_arm_name = best
                        # Check if any metric is NaN, implying fallback to raw observed data or model failure
                        if best_metrics and isinstance(best_metrics, dict):
                            model_used = not any(
                                isinstance(v, float) and np.isnan(v)
                                or (isinstance(v, tuple) and any(np.isnan(x) for x in v))
                                for v in best_metrics.values()
                            )
                except Exception as e:
                    print(f"[WARNING] Failed to get best parameterization: {e}")

            status = {
                "running": self.platform_running,
                "config_ready": self.config_ready,
                "awaiting_result": self.awaiting_result,
                "timestamp": time.time(),
                "best_suggestion": best_params,
                "best_estimation": best_metrics,
                "best_trial_index": best_trial_index,
                "best_arm_name": best_arm_name,
                "model_used_in_best_estimation": model_used,
            }

            self.mqtt_handler.publish("platform_status", status)

            time.sleep(5)

    def send_suggestion(self):
        if not self.optimizer:
            print("[SUGGESTION] Optimizer not initialized. Skipping suggestion.")
            return
        # if self.awaiting_result:
        #     print("[SUGGESTION] Awaiting result from last trial. Not suggesting new one.")
        #     return

        trial_index, suggestion = self.optimizer.suggest_next()
        if suggestion:
            # Round all float values to 2 decimal places
            rounded_suggestion = {
            k: round(v, 2) if isinstance(v, float) else v
            for k, v in suggestion.items()
             }
            self.last_suggestion = rounded_suggestion
            self.awaiting_result = True
            self.mqtt_handler.publish("input", rounded_suggestion)
            # Publish optimizer state to data topic
            self.publish_optimizer_state()

    def _optimizer_status(self, msg):
        self.mqtt_handler.publish("platform_status", msg)
    
    def publish_optimizer_state(self):
        if not self.optimizer:
            self.mqtt_handler.publish("data", {"error": "Optimizer not initialized."})
            return

        try:
            df = self.optimizer.custom_summarize()
            trial_array = df.values
            # Get parameter and metric names from the experiment definition
            param_names = [p.name for p in self.optimizer.client._experiment.search_space.parameters.values()]
            metric_names = list(self.optimizer.client._experiment.metrics.keys())
            trial_list = []
            for row in trial_array:
                trial_dict = {}
                parameters = {}
                metrics = {}
                
                for col, val in zip(df.columns, row):
                    if isinstance(val, float):
                        val = round(val, 2)
                    if col in param_names:
                        parameters[col] = val
                    elif col in metric_names:
                        metrics[col] = val
                    else:
                        trial_dict[col] = val
                
                trial_dict["parameters"] = parameters
                trial_dict["metrics"] = metrics
                trial_list.append(trial_dict)

            self.mqtt_handler.publish("data", {"trials": trial_list})

        except Exception as e:
            self.mqtt_handler.publish("data", {"error": str(e)})

