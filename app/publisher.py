"""
Publisher: simulates event traffic by sending messages to a GCP Pub/Sub topic.
Supports three load patterns to realistically demo autoscaling:
  - steady: fixed rate forever
  - burst: sudden spike then quiet
  - ramp: gradually increasing rate
"""
import os
import time
import argparse
from google.cloud import pubsub_v1

def get_config():
    return {
        "project_id": os.environ["GCP_PROJECT_ID"],
        "topic_name": os.environ["TOPIC_NAME"],
    }

def publish_message(publisher, topic_path, message_id):
    data = f"event-{message_id}".encode("utf-8")
    future = publisher.publish(topic_path, data)
    return future.result()  # blocks until ack from Pub/Sub, raises on failure

def run_steady(publisher, topic_path, rate_per_sec):
    msg_id = 0
    while True:
        publish_message(publisher, topic_path, msg_id)
        msg_id += 1
        time.sleep(1 / rate_per_sec)

def run_burst(publisher, topic_path, burst_size, quiet_seconds):
    msg_id = 0
    while True:
        print(f"[burst] sending {burst_size} messages")
        for _ in range(burst_size):
            publish_message(publisher, topic_path, msg_id)
            msg_id += 1
        print(f"[burst] quiet for {quiet_seconds}s")
        time.sleep(quiet_seconds)

def run_ramp(publisher, topic_path, start_rate, max_rate, step_seconds):
    msg_id = 0
    rate = start_rate
    while True:
        publish_message(publisher, topic_path, msg_id)
        msg_id += 1
        time.sleep(1 / rate)
        if msg_id % 20 == 0 and rate < max_rate:
            rate += 1
            print(f"[ramp] rate now {rate}/sec")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["steady", "burst", "ramp"], default="steady")
    parser.add_argument("--rate", type=float, default=1.0)
    args = parser.parse_args()

    config = get_config()
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(config["project_id"], config["topic_name"])

    if args.mode == "steady":
        run_steady(publisher, topic_path, args.rate)
    elif args.mode == "burst":
        run_burst(publisher, topic_path, burst_size=50, quiet_seconds=20)
    elif args.mode == "ramp":
        run_ramp(publisher, topic_path, start_rate=1, max_rate=20, step_seconds=1)
