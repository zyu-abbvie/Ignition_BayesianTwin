import paho.mqtt.client as mqtt
import json
import threading


class MQTTHandler:
    def __init__(self, broker, port, username, password, topics):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.topics = topics  # dict: {'trigger': '...', 'input': '...', etc.}
        self.client = mqtt.Client()
        self.client.username_pw_set(self.username, self.password)

        self.message_callback = None
        self.status_callback = None
        self._lock = threading.Lock()

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def set_message_callback(self, callback):
        self.message_callback = callback

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Connected with result code {rc}")
        for topic in self.topics.values():
            self.client.subscribe(topic)
            print(f"[MQTT] Subscribed to: {topic}")

    def _on_message(self, client, userdata, msg):
        raw_payload = msg.payload.decode()
        print(f"[MQTT] Message received on {msg.topic}: '{raw_payload}'")

        if not raw_payload.strip():
            self.publish_status("status", {
                "status": "error",
                "message": "Empty payload received; cannot decode"
            })
            return

        try:
            data = json.loads(raw_payload)
        except json.JSONDecodeError as e:
            self.publish_status("status", {
                "status": "error",
                "message": f"JSON decode error: {str(e)}. Raw: '{raw_payload}'"
            })
            return

        with self._lock:
            if self.message_callback:
                self.message_callback(topic=msg.topic, payload=data)

    def connect(self):
        try:
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            print("[MQTT] Connection established and loop started")
        except Exception as e:
            print(f"[MQTT ERROR] Could not connect: {e}")

    def publish(self, topic_key, data):
        if topic_key not in self.topics:
            print(f"[MQTT WARNING] Unknown topic key: {topic_key}")
            return
        topic = self.topics[topic_key]
        try:
            payload = json.dumps(data) if not isinstance(data, str) else data
            self.client.publish(topic, payload, retain=True)
            print(f"[MQTT] Published to {topic}: {payload}")
        except Exception as e:
            print(f"[MQTT ERROR] Failed to publish to {topic}: {e}")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
        print("[MQTT] Disconnected cleanly")
